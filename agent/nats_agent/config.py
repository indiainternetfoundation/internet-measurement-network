import configparser
import uuid
from pathlib import Path
import structlog # Import structlog directly

# Get logger instance (assuming setup_logging was called)
log = structlog.get_logger("agent.config")

CONFIG_FILE_NAME = "agent_config.ini"

def load_or_create_config(config_dir: Path, filename: str = CONFIG_FILE_NAME) -> tuple[configparser.ConfigParser, str]:
    """Loads configuration from a file or creates it if it doesn't exist."""
    if not isinstance(config_dir, Path):
        config_dir = Path(config_dir) # Ensure it's a Path object

    config_path = config_dir / filename
    config = configparser.ConfigParser()
    agent_id = None
    created_new = False

    config_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists

    if config_path.exists():
        try:
            config.read(config_path)
            if 'Agent' in config and 'id' in config['Agent']:
                agent_id = config['Agent']['id']
                try:
                    uuid.UUID(agent_id) # Validate it's a UUID
                    log.info("Loaded configuration file.", path=str(config_path), agent_id=agent_id)
                except ValueError:
                    log.warning("Invalid Agent ID found in config, generating a new one.", path=str(config_path), invalid_id=agent_id)
                    agent_id = None # Force regeneration
            else:
                 log.warning("Config file found but missing [Agent] section or 'id', generating new ID.", path=str(config_path))
                 # Agent section or id might be missing, ensure it's created below
        except configparser.Error as e:
            log.error("Failed to read config file, will try to recreate.", path=str(config_path), error=str(e))
            agent_id = None # Force regeneration

    if agent_id is None:
        agent_id = str(uuid.uuid4())
        if 'Agent' not in config:
            config.add_section('Agent')
        config['Agent']['id'] = agent_id
        try:
            with open(config_path, 'w') as configfile:
                config.write(configfile)
            log.info("Created/updated configuration file with Agent ID.", path=str(config_path), agent_id=agent_id)
            created_new = True
        except OSError as e:
             log.error("Failed to write config file.", path=str(config_path), error=str(e))
             # Agent will run with generated ID but it won't be saved
             log.warning("Agent ID will not be persisted across restarts.", agent_id=agent_id)


    # Add other default sections/values if needed and save if new
    # Example: ensure NATS section exists
    # modified = False
    # if 'NATS' not in config:
    #     config.add_section('NATS')
    #     config['NATS']['default_url'] = 'nats://localhost:4222'
    #     modified = True
    #
    # if modified and not created_new: # Save only if modified and not just created
    #     try:
    #         with open(config_path, 'w') as configfile:
    #             config.write(configfile)
    #         log.info("Updated config file with default sections.", path=str(config_path))
    #     except OSError as e:
    #         log.error("Failed to write updated config file.", path=str(config_path), error=str(e))


    return config, agent_id