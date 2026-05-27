from config_management.config_registry import (
    build_central_config_registry,
    create_config_record,
    get_config_value,
    upsert_config_record,
)


def test_config_registry_get_value():
    registry = build_central_config_registry(
        records=[
            create_config_record(key="max_leverage", value=10, value_type="int", scope="risk")
        ]
    )

    assert get_config_value(registry, "max_leverage", scope="risk") == 10


def test_config_registry_upsert():
    registry = build_central_config_registry(
        records=[
            create_config_record(key="profile", value="conservative", scope="strategy")
        ]
    )

    updated = upsert_config_record(
        registry,
        create_config_record(key="profile", value="balanced", scope="strategy"),
    )

    assert get_config_value(updated, "profile", scope="strategy") == "balanced"


def test_config_registry_bool_cast():
    registry = build_central_config_registry(
        records=[
            create_config_record(key="dry_run", value="true", value_type="bool", scope="execution")
        ]
    )

    assert get_config_value(registry, "dry_run", scope="execution") is True