from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
UES_SRC = ROOT.parent / "UsEquityStrategies" / "src"

for candidate in (ROOT, QPK_SRC, UES_SRC):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from quant_platform_kit.common.strategies import derive_strategy_artifact_paths  # noqa: E402
from strategy_registry import (  # noqa: E402
    SCHWAB_PLATFORM,
    get_platform_profile_status_matrix,
    resolve_strategy_definition,
    resolve_strategy_metadata,
)
from us_equity_strategies import get_strategy_catalog  # noqa: E402
from us_equity_strategies.runtime_adapters import describe_platform_runtime_requirements  # noqa: E402


def build_switch_plan(profile: str) -> dict[str, object]:
    definition = resolve_strategy_definition(profile, platform_id=SCHWAB_PLATFORM)
    metadata = resolve_strategy_metadata(definition.profile, platform_id=SCHWAB_PLATFORM)
    status_row = next(
        row for row in get_platform_profile_status_matrix() if row["canonical_profile"] == definition.profile
    )
    artifact_paths = derive_strategy_artifact_paths(
        get_strategy_catalog(),
        definition.profile,
        repo_root=ROOT,
    )
    runtime_requirements = describe_platform_runtime_requirements(
        definition.profile,
        platform_id=SCHWAB_PLATFORM,
    )
    requires_feature_snapshot = bool(runtime_requirements["requires_snapshot_artifacts"])
    requires_snapshot_manifest_path = bool(
        runtime_requirements["requires_snapshot_manifest_path"]
    )
    requires_strategy_config_path = bool(runtime_requirements["requires_strategy_config_path"])
    config_source_policy = str(runtime_requirements.get("config_source_policy") or "none")

    set_env: dict[str, str] = {"STRATEGY_PROFILE": definition.profile}
    keep_env: list[str] = []
    optional_env = [
        "SCHWAB_DRY_RUN_ONLY",
        "SCHWAB_MIN_RESERVED_CASH_USD",
        "SCHWAB_RESERVED_CASH_RATIO",
    ]
    remove_if_present: list[str] = []
    notes = [
        "Schwab has a single service identity, so strategy switching mainly changes STRATEGY_PROFILE and any snapshot-config envs.",
    ]

    if requires_feature_snapshot:
        set_env["SCHWAB_FEATURE_SNAPSHOT_PATH"] = "<required>"
        if requires_snapshot_manifest_path:
            set_env["SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH"] = "<required>"
        else:
            remove_if_present.append("SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH")
        if requires_strategy_config_path and config_source_policy == "env_only":
            set_env["SCHWAB_STRATEGY_CONFIG_PATH"] = "<required>"
        elif requires_strategy_config_path and config_source_policy == "bundled_or_env":
            remove_if_present.append("SCHWAB_STRATEGY_CONFIG_PATH")
            notes.append(
                "SCHWAB_STRATEGY_CONFIG_PATH is optional for bundled_or_env profiles; leave it unset to use the packaged canonical config."
            )
        elif requires_strategy_config_path:
            set_env["SCHWAB_STRATEGY_CONFIG_PATH"] = "<required>"
        else:
            remove_if_present.append("SCHWAB_STRATEGY_CONFIG_PATH")
    else:
        remove_if_present.extend(
            [
                "SCHWAB_FEATURE_SNAPSHOT_PATH",
                "SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH",
                "SCHWAB_STRATEGY_CONFIG_PATH",
            ]
        )

    hints: dict[str, str] = {}
    if requires_feature_snapshot:
        hints["feature_snapshot_filename"] = f"{definition.profile}_feature_snapshot_latest.csv"
        hints["feature_snapshot_manifest_filename"] = (
            f"{definition.profile}_feature_snapshot_latest.csv.manifest.json"
        )
    if artifact_paths.bundled_config_path is not None:
        hints["bundled_strategy_config_path"] = str(artifact_paths.bundled_config_path)

    return {
        "platform": SCHWAB_PLATFORM,
        "canonical_profile": definition.profile,
        "display_name": metadata.display_name,
        "eligible": status_row["eligible"],
        "enabled": status_row["enabled"],
        **runtime_requirements,
        "required_inputs": sorted(definition.required_inputs),
        "target_mode": definition.target_mode,
        "set_env": set_env,
        "keep_env": keep_env,
        "optional_env": sorted(optional_env),
        "remove_if_present": sorted(set(remove_if_present)),
        "hints": hints,
        "notes": notes,
    }


def _print_plan(plan: dict[str, object]) -> None:
    print(f"platform: {plan['platform']}")
    print(f"profile: {plan['canonical_profile']} ({plan['display_name']})")
    print(f"eligible: {plan['eligible']}  enabled: {plan['enabled']}")
    print(f"profile_group: {plan['profile_group']}")
    print(f"required_inputs: {', '.join(plan['required_inputs'])}")
    print(f"input_mode: {plan['input_mode']}")
    print(f"requires_snapshot_artifacts: {plan['requires_snapshot_artifacts']}")
    print(f"requires_strategy_config_path: {plan['requires_strategy_config_path']}")
    print(f"target_mode: {plan['target_mode']}")
    print("\nset_env:")
    for key, value in plan["set_env"].items():
        print(f"  {key}={value}")
    print("\nkeep_env:")
    for key in plan["keep_env"]:
        print(f"  {key}")
    print("\noptional_env:")
    for key in plan["optional_env"]:
        print(f"  {key}")
    print("\nremove_if_present:")
    for key in plan["remove_if_present"]:
        print(f"  {key}")
    if plan["hints"]:
        print("\nhints:")
        for key, value in plan["hints"].items():
            print(f"  {key}: {value}")
    if plan["notes"]:
        print("\nnotes:")
        for note in plan["notes"]:
            print(f"  - {note}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plan = build_switch_plan(args.profile)
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    _print_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
