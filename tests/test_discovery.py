from vantadsp.discovery import _windows_jbl_row, detect_jbl_device


def test_detects_pid_from_harman_manufacturer_data():
    result = detect_jbl_device(
        {
            "name": "JBL Charge6",
            "service_uuids": [],
            "service_data": {},
            "manufacturer_data": {"87": "e320010000"},
        }
    )
    assert result == {
        "is_jbl": True,
        "pid": "20e3",
        "model": "JBL Charge 6",
        "confidence": "high",
        "reason": "Harman company data",
    }


def test_detects_protocol4_and_pro_service_data():
    protocol4 = detect_jbl_device(
        {
            "name": "",
            "service_uuids": [],
            "service_data": {"0000fddf-0000-1000-8000-00805f9b34fb": "32210000"},
            "manufacturer_data": {},
        }
    )
    pro = detect_jbl_device(
        {
            "name": "",
            "service_uuids": [],
            "service_data": {"0000dffd-0000-1000-8000-00805f9b34fb": "00e32000"},
            "manufacturer_data": {},
        }
    )
    assert (protocol4["pid"], protocol4["reason"]) == ("2132", "FDDF service data")
    assert (pro["pid"], pro["reason"]) == ("20e3", "DFFD service data")


def test_detects_model_specific_service_uuid():
    result = detect_jbl_device(
        {
            "name": "",
            "service_uuids": ["65786365-6c70-6f69-6e74-2e04ffe32001"],
            "service_data": {},
            "manufacturer_data": {},
        }
    )
    assert result["pid"] == "20e3"
    assert result["reason"] == "model-specific service UUID"


def test_name_is_safe_fallback_but_ambiguous_revision_is_not_guessed():
    unique = detect_jbl_device({"name": "JBLCharge6", "service_uuids": [], "service_data": {}, "manufacturer_data": {}})
    ambiguous = detect_jbl_device(
        {"name": "JBL GO 4", "service_uuids": [], "service_data": {}, "manufacturer_data": {}}
    )
    unrelated = detect_jbl_device(
        {"name": "Wireless Mouse", "service_uuids": [], "service_data": {}, "manufacturer_data": {}}
    )
    assert (unique["pid"], unique["confidence"]) == ("20e3", "medium")
    assert ambiguous["is_jbl"] is True and ambiguous["pid"] is None
    assert unrelated["is_jbl"] is False and unrelated["pid"] is None


def test_windows_paired_metadata_recovers_pid_and_address():
    row = _windows_jbl_row(
        r"\\?\BTHENUM#{0000110b-0000}_VID&00010ecb_PID&20e3#8&abc&0&A1B2C3D4E5F6_C00000000#{guid}",
        "JBLSBIC",
    )
    assert row is not None
    assert row["address"] == "A1:B2:C3:D4:E5:F6"
    assert row["jbl_detection"] == {
        "is_jbl": True,
        "pid": "20e3",
        "model": "JBL Charge 6",
        "confidence": "high",
        "reason": "Windows paired-device metadata",
    }
    assert _windows_jbl_row(r"\\?\USB#VID_0ECB&PID_20E3", "JBL Charge 6") is None
