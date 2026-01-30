import getpass
import grp
import os
import platform
import pwd
from typing import Mapping

from heartbeat.model import Modules, NetworkInterface, System, Loadavg, User, ModuleSpecification

def _safe_get_user_info(module) -> User:
    """Safely collects user information."""
    try:
        user_name = getpass.getuser()
        user_pw = pwd.getpwnam(user_name)
        primary_gid = user_pw.pw_gid
        user_pw = pwd.getpwnam(user_name)
        try:
            user_groups_ids = os.getgrouplist(user_name, primary_gid)
            groups = [
                grp.getgrgid(gid).gr_name for gid in user_groups_ids if gid
            ]  # Filter potential None gids
        except Exception as ge:
            module.logger.warning(
                f"Could not get group list of user {user_name} while sending heartbeat"
            )
            groups = ["Error"]

        return User(
            user = user_pw.pw_name,
            working_dir = os.getcwd(),
            home_dir = user_pw.pw_dir,
            shell = user_pw.pw_shell,
            uid = user_pw.pw_uid,
            gid = primary_gid,
            gecos = user_pw.pw_gecos,
            groups = groups,
            loadavg = Loadavg(**dict(zip(["1m", "5m", "15m"], os.getloadavg()))) if hasattr(os, "getloadavg") else None,
        )
    except (KeyError, AttributeError, OSError) as e:
        module.logger.warning(
            f"Could not get full user info of user {getpass.getuser()} while sending heartbeat"
        )
        return {"user": getpass.getuser(), "error": f"Partial info: {e}"}
    except Exception as e:
        module.logger.error(
            "Unexpected error getting user info while sending heartbeat"
        )
        return {"error": f"Unexpected: {e}"}

def _safe_get_system_info(module) -> System:
    """Safely collects system information."""
    try:
        return System(
            system = platform.system(),
            node_name = platform.node(),
            release = platform.release(),
            version = platform.version(),
            machine = platform.machine(),
            processor = platform.processor(),  # Can be empty string
            platform = platform.platform(),  # Can be empty string
        )
    except Exception as e:
        module.logger.error("Error getting system info while sending heartbeat")
        return {"error": str(e)}

def _safe_get_network_info(module) -> Mapping[str, NetworkInterface]:
    """Safely collects network interface information."""
    try:
        import netifaces
    except:
        return {}

    interfaces_data = {}
    try:
        available_interfaces = netifaces.interfaces()
    except Exception as e:
        module.logger.error(
            "Could not list network interfaces while sending heartbeat"
        )
        return {"error": f"Cannot list interfaces: {e}"}

    for interface in available_interfaces:
        try:
            addresses = netifaces.ifaddresses(interface)
            # Use dict comprehension for cleaner extraction, provide empty list default
            interfaces_data[interface] = {
                "ipv4": [
                    addr["addr"]
                    for addr in addresses.get(netifaces.AF_INET, [])
                    if "addr" in addr
                ],
                "ipv6": [
                    addr["addr"]
                    for addr in addresses.get(netifaces.AF_INET6, [])
                    if "addr" in addr
                ],
                "mac": [
                    addr["addr"]
                    for addr in addresses.get(netifaces.AF_LINK, [])
                    if "addr" in addr
                ],
            }
            # Handle Linux AF_PACKET explicitly if AF_LINK is not present or empty
            if netifaces.AF_LINK in addresses and not interfaces_data[
                interface
            ].get("mac"):
                interfaces_data[interface]["mac"] = [
                    addr["addr"]
                    for addr in addresses.get(netifaces.AF_LINK, [])
                    if "addr" in addr
                ]

        except Exception as ie:
            module.logger.error(
                f"Error retrieving info for interface {interface} while sending heartbeat"
            )
            interfaces_data[interface] = {"error": f"Retrieval failed: {ie}"}

    return { interface_name: NetworkInterface(**interface_data) for interface_name, interface_data in interfaces_data.items()}

def _safe_agent_version(module):
    return {}

def _safe_loaded_modules(module) -> Modules:
    workers = module.agent.manager.running_workers
    return Modules(
        modules = list(workers.keys()),
        spec = {
            worker_name: ModuleSpecification(
                input_schema=worker.serializer().schema(),
                input_subject=worker.sub_in,
                output_subject=worker.sub_out,
                error_subject=worker.sub_err
            ) 
            for (worker_name, worker) in workers.items() if worker.serializer()
        }
    )