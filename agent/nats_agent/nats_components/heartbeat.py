import asyncio
import time
import platform
import os
import getpass
import grp
import pwd
import netifaces
import structlog
import nats
from typing import Callable
from nats.errors import ConnectionClosedError

# Import base class and metrics
from .base import Publisher
from .. import metrics

log = structlog.get_logger("agent.heartbeat")

class HeartbeatPublisher(Publisher):
    """Publishes agent status periodically."""
    def __init__(self, nc: nats.NATS, agent_id: str, agent_name: str, subject: str, interval: int, error_handler: Callable):
        super().__init__(nc, agent_id, agent_name, subject, error_handler=error_handler)
        if interval <= 0:
            raise ValueError("Heartbeat interval must be positive")
        self.interval = interval

        self.metadata_func = []

        # Bind additional context to the logger for this specific component
        self.log = self.log.bind(agent_name=agent_name, interval_sec=interval)
    
    def add_metadata(self, func):
        if callable(func):
            self.metadata_func.append(func)
        else:
            self.metadata_func.append(lambda : func)

    def _safe_get_user_info(self):
        """Safely collects user information."""
        try:
            user_name = getpass.getuser()
            user_pw = pwd.getpwnam(user_name)
            primary_gid = user_pw.pw_gid
            try:
                user_groups_ids = os.getgrouplist(user_name, primary_gid)
                groups = [grp.getgrgid(gid).gr_name for gid in user_groups_ids if gid] # Filter potential None gids
            except Exception as ge:
                self.log.warning("Could not get group list", user=user_name, error=str(ge))
                groups = ["Error"]

            return {
                "user": user_pw.pw_name,
                "working_dir": os.getcwd(),
                "home_dir": user_pw.pw_dir,
                "shell": user_pw.pw_shell,
                "uid": user_pw.pw_uid,
                "gid": primary_gid,
                "gecos": user_pw.pw_gecos,
                "groups": groups,
                "loadavg": dict(zip(["1m", "5m", "15m"], os.getloadavg())) if hasattr(os, 'getloadavg') else None,
            }
        except (KeyError, AttributeError, OSError) as e:
             self.log.warning("Could not get full user info", user=getpass.getuser(), error=str(e))
             metrics.ERRORS_COUNTER.labels(type='user_info_error').inc()
             return { "user": getpass.getuser(), "error": f"Partial info: {e}"}
        except Exception as e:
            self.log.error("Unexpected error getting user info", error=str(e), exc_info=True)
            metrics.ERRORS_COUNTER.labels(type='user_info_error').inc()
            return {"error": f"Unexpected: {e}"}

    def _safe_get_system_info(self):
        """Safely collects system information."""
        try:
            return {
                "system": platform.system(),
                "node_name": platform.node(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(), # Can be empty string
                "platform": platform.platform(), # Can be empty string
            }
        except Exception as e:
            self.log.error("Error getting system info", error=str(e), exc_info=True)
            metrics.ERRORS_COUNTER.labels(type='system_info_error').inc()
            return {"error": str(e)}

    def _safe_get_network_info(self):
        """Safely collects network interface information."""
        interfaces_data = {}
        try:
            available_interfaces = netifaces.interfaces()
        except Exception as e:
             self.log.error("Could not list network interfaces", error=str(e))
             metrics.ERRORS_COUNTER.labels(type='network_info_error').inc()
             return {"error": f"Cannot list interfaces: {e}"}

        for interface in available_interfaces:
            try:
                addresses = netifaces.ifaddresses(interface)
                # Use dict comprehension for cleaner extraction, provide empty list default
                interfaces_data[interface] = {
                    "ipv4": [addr['addr'] for addr in addresses.get(netifaces.AF_INET, []) if 'addr' in addr],
                    "ipv6": [addr['addr'] for addr in addresses.get(netifaces.AF_INET6, []) if 'addr' in addr],
                    "mac": [addr['addr'] for addr in addresses.get(netifaces.AF_LINK, []) if 'addr' in addr],
                }
                # Handle Linux AF_PACKET explicitly if AF_LINK is not present or empty
                if netifaces.AF_PACKET in addresses and not interfaces_data[interface].get("mac"):
                     interfaces_data[interface]["mac"] = [addr['addr'] for addr in addresses.get(netifaces.AF_PACKET, []) if 'addr' in addr]

            except Exception as ie:
                self.log.warning("Error retrieving info for interface", interface=interface, error=str(ie))
                interfaces_data[interface] = {"error": f"Retrieval failed: {ie}"}

        return interfaces_data

    def _get_agent_info(self):
        """Constructs the complete heartbeat data payload."""
        return {
            "id": self.agent_id,
            "name": self.agent_name,
            "timezone": time.tzname, # Tuple like ('IST', 'IST') - might need formatting
            "user": self._safe_get_user_info(),
            "system": self._safe_get_system_info(),
            "network": self._safe_get_network_info(),
            "metadata": [func() for func in self.metadata_func]
        }

    async def start_publishing(self):
        """Overrides base method to continuously publish heartbeats."""
        self.log.info("Starting heartbeat publisher loop")
        while True:
            start_time = asyncio.get_event_loop().time()
            try:
                if not self.nc or not self.nc.is_connected:
                     self.log.warning("Heartbeat skipped: NATS not connected.")
                     metrics.NATS_CONNECTION_STATUS.set(0)
                     # Wait full interval before next check if disconnected
                     await asyncio.sleep(self.interval)
                     continue # Skip to next iteration

                heartbeat_data = self._get_agent_info()
                await self.publish(heartbeat_data) # Publish calls log.debug
                metrics.HEARTBEATS_SENT.inc()

                # Calculate time elapsed and sleep for the remaining interval
                elapsed_time = asyncio.get_event_loop().time() - start_time
                sleep_duration = max(0, self.interval - elapsed_time)
                await asyncio.sleep(sleep_duration)

            except ConnectionClosedError:
                # Publish already logs this, but good to know the loop was interrupted
                self.log.error("Heartbeat loop interrupted: NATS Connection closed.")
                metrics.NATS_CONNECTION_STATUS.set(0)
                # Wait before retrying connection/publish in the next loop iteration
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                 self.log.info("Heartbeat publisher task cancelled.")
                 break # Exit the loop cleanly
            except Exception as e:
                self.log.error("Heartbeat publisher encountered an unexpected error", error=str(e), exc_info=True)
                metrics.ERRORS_COUNTER.labels(type='heartbeat_loop').inc()
                # Avoid tight loop on persistent errors, wait before next attempt
                await asyncio.sleep(self.interval)
        self.log.info("Heartbeat publisher loop stopped.")