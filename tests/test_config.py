from sheet_dj.config import Config


def test_defaults() -> None:
    assert Config.from_env({}) == Config(port=5118, idle_minutes=20, max_upload_mb=20, max_files=20)


def test_environment_overrides() -> None:
    env = {"SHEETDJ_PORT": "6000", "SHEETDJ_MAX_FILES": "3"}
    config = Config.from_env(env)
    assert (config.port, config.max_files, config.max_upload_mb) == (6000, 3, 20)
