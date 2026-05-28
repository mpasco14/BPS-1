from data_persistence.artifact_indexer import (
    ArtifactIndexerConfig,
    build_artifact_index_report,
    export_artifact_index_report,
)


def test_artifact_indexer_indexes_files(tmp_path):
    (tmp_path / "report.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "events.jsonl").write_text('{"x": 1}\n', encoding="utf-8")

    report = build_artifact_index_report(
        root=tmp_path,
        config=ArtifactIndexerConfig(artifact_root=tmp_path),
    )

    assert report.artifacts_count == 2
    assert report.by_kind["json"] == 1
    assert report.by_kind["jsonl"] == 1


def test_artifact_indexer_export(tmp_path):
    (tmp_path / "report.json").write_text('{"ok": true}', encoding="utf-8")

    report = build_artifact_index_report(
        root=tmp_path,
        config=ArtifactIndexerConfig(artifact_root=tmp_path),
    )

    path = export_artifact_index_report(report, path=tmp_path / "index.json")

    assert path.exists()