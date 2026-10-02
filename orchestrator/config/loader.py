from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class OrchestratorConfig:
    restricted_actions: frozenset[str] = frozenset({"live_order","live_withdrawal","live_account_mutation","production_deploy","policy_change","merge_pr"})
    require_verification: bool = True

def load_config(path=None):
    if path is None or not Path(path).exists(): return OrchestratorConfig()
    values={}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key,value=line.split(":",1); values[key.strip()]=value.strip().strip('"\'')
    restricted=values.get("restricted_actions")
    actions=frozenset(x.strip() for x in restricted.strip("[]").split(",") if x.strip()) if restricted else OrchestratorConfig().restricted_actions
    return OrchestratorConfig(actions, values.get("require_verification","true").lower() == "true")
