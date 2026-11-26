from pricing_demo.domain.package_fingerprint import PackageFingerprint, instance_defaults


def test_a_fingerprint_holds_what_the_worker_read() -> None:
    fingerprint = PackageFingerprint("abc", "0.1.0", "deadbeef", False, {"InstanceParams": {}})

    assert (fingerprint.fingerprint, fingerprint.version) == ("abc", "0.1.0")
    assert (fingerprint.git_commit, fingerprint.git_dirty) == ("deadbeef", False)


def test_the_park_times_are_the_minute_columns_and_the_rest_keeps_its_name() -> None:
    defaults = {
        "PipelineConfig": {"clustering_threshold_m": 500.0, "otp_workers": 4},
        "InstanceParams": {"fixed_capacity": 20, "min_park_time": 1.0, "max_park_time": 5.0},
        "OptimizerParams": {"theta": 0.5},
    }

    assert instance_defaults(defaults) == {
        "clustering_threshold_m": 500.0,
        "fixed_capacity": 20,
        "min_park_time_min": 1.0,
        "max_park_time_min": 5.0,
    }


def test_a_missing_group_gives_no_values() -> None:
    assert instance_defaults({}) == {}
