import shutil

from sqlalchemy import func, select

from app.ai import registry, seed
from app.ai.models import Prompt, PromptVersion

EXPECTED = {
    "doc.classify", "doc.read.passport", "doc.read.arrival_record", "doc.read.employer_letter",
    "doc.read.pay_statement", "doc.read.prior_notice", "doc.read.certified_translation", "doc.read.generic",
    "doc.read.zoom_notes", "doc.read.whatsapp_chat", "doc.read.email_message",
}

N = len(list(seed.PROMPTS_DIR.glob("*.yaml")))


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_seed_inserts_all_missing_keys(session_factory):
    with session_factory() as db:
        added = seed.seed_prompts(db)
        assert EXPECTED <= set(added) and len(added) == N
        assert count(db, Prompt) == N
        for prompt in db.scalars(select(Prompt)):
            version = db.get(PromptVersion, prompt.active_version_id)
            assert version.version == 1
            assert version.created_by == "seed"


def test_seed_is_idempotent(session_factory):
    with session_factory() as db:
        seed.seed_prompts(db)
        assert seed.seed_prompts(db) == []
        assert count(db, Prompt) == N
        assert count(db, PromptVersion) == N


def test_missing_key_is_inserted_and_others_untouched(session_factory, tmp_path):
    for path in seed.PROMPTS_DIR.glob("*.yaml"):
        if path.name != "read_prior_notice.yaml":
            (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with session_factory() as db:
        assert len(seed.seed_prompts(db, tmp_path)) == N - 1
        assert seed.seed_prompts(db) == ["doc.read.prior_notice"]
        assert count(db, Prompt) == N


def test_existing_key_never_overwritten_after_edit(session_factory):
    with session_factory() as db:
        seed.seed_prompts(db)
        prompt = db.scalar(select(Prompt).where(Prompt.key == "doc.read.passport"))
        old = db.get(PromptVersion, prompt.active_version_id)
        data = {k: getattr(old, k) for k in seed._VERSION_FIELDS}
        row = registry.create_version([{"version": 1}], data, data | {"system_text": "EDITED", "created_by": "ops"})
        new = PromptVersion(prompt_id=prompt.id, **row)
        db.add(new)
        db.flush()
        prompt.active_version_id = new.id
        prompt.title = "Edited title"
        db.commit()
        assert seed.seed_prompts(db) == []
        db.expire_all()
        prompt = db.scalar(select(Prompt).where(Prompt.key == "doc.read.passport"))
        assert prompt.title == "Edited title"
        assert db.get(PromptVersion, prompt.active_version_id).system_text == "EDITED"
        assert db.scalar(select(func.count()).select_from(PromptVersion).where(PromptVersion.prompt_id == prompt.id)) == 2


def test_missing_directory_adds_nothing(session_factory, tmp_path):
    with session_factory() as db:
        assert seed.seed_prompts(db, tmp_path / "nope") == []


def test_custom_directory_only_seeds_its_files(session_factory, tmp_path):
    shutil.copy(seed.PROMPTS_DIR / "read_generic.yaml", tmp_path / "read_generic.yaml")
    with session_factory() as db:
        assert seed.seed_prompts(db, tmp_path) == ["doc.read.generic"]
