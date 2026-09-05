from clearing_ingest.filespec import LogicalFile
from clearing_ingest.generator import build_logical_file


def test_header_trailer_file_ids_match_on_clean_file():
    logical = build_logical_file(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        member_id="M-NORTH",
    )
    assert logical.header.file_id == logical.trailer.file_id
    assert logical.trailer.message_count == len(logical.messages)
    assert [m.message_no for m in logical.messages] == list(range(1, len(logical.messages) + 1))


def test_poison_header_trailer_mismatch():
    logical = build_logical_file(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        member_id="M-NORTH",
        fault="header_trailer_mismatch",
    )
    assert logical.header.file_id != logical.trailer.file_id
    LogicalFile.model_validate(logical.model_dump())
