import uuid
from typing import Annotated, Optional
from ipaddress import IPv4Address, IPv6Address

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

from aiori_agent.utils import get_model_name

# Below regex has been taken from https://github.com/acidjunk/cnaas-nms/blob/41c95beb66c77cce921f169860ff474d4117ffda/src/cnaas_nms/db/settings_fields.py#L16
IPV4_REGEX = r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}" r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
# IPv6 regex from https://stackoverflow.com/questions/53497/regular-expression-that-matches-valid-ipv6-addresses
#  minus IPv4 mapped etc since we probably can't handle them anyway
IPV6_REGEX = (
    r"(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|"  # 1:2:3:4:5:6:7:8
    r"([0-9a-fA-F]{1,4}:){1,7}:|"  # 1::                              1:2:3:4:5:6:7::
    r"([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"  # 1::8             1:2:3:4:5:6::8  1:2:3:4:5:6::8
    r"([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|"  # 1::7:8           1:2:3:4:5::7:8  1:2:3:4:5::8
    r"([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|"  # 1::6:7:8         1:2:3:4::6:7:8  1:2:3:4::8
    r"([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|"  # 1::5:6:7:8       1:2:3::5:6:7:8  1:2:3::8
    r"([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|"  # 1::4:5:6:7:8     1:2::4:5:6:7:8  1:2::8
    r"[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|"  # 1::3:4:5:6:7:8   1::3:4:5:6:7:8  1::8
    r":((:[0-9a-fA-F]{1,4}){1,7}|:))"
)
HOSTNAME_REGEX = r"^([a-zA-Z0-9-]{1,63})(\.[a-zA-Z-][a-zA-Z0-9-]{0,62})*$"
DOMAIN_NAME_REGEX = r"^([a-zA-Z0-9-]{1,63})(\.[a-zA-Z0-9-]{1,63})+$"

IPv4    = Annotated[str, Field(pattern=IPV4_REGEX, json_schema_extra={ 'format': 'ipv4',  })]
IPv6    = Annotated[str, Field(pattern=IPV6_REGEX, json_schema_extra={ 'format': 'ipv6',  })]
Hostname = Annotated[str, Field(pattern=HOSTNAME_REGEX, json_schema_extra={ 'format': 'hostname',  })]
Domain = Annotated[str, Field(pattern=DOMAIN_NAME_REGEX, json_schema_extra={ 'format': 'domain',  })]

class MeasurementQuery(BaseModel):
    id: SkipJsonSchema[Optional[uuid.UUID]] = Field(default_factory=uuid.uuid4)
    # id: Annotated[SkipJsonSchema[str], Field(default_factory=lambda: uuid.uuid4().hex)]
    # type: Optional[str] = Field(default_factory=get_model_name)

    # @computed_field
    # @property
    @classmethod
    def model_type(cls) -> str:
        return get_model_name(cls)