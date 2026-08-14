import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wave40InboxCrmTriageContractTests(unittest.TestCase):
    def test_triage_exposes_explicit_contact_and_followup_actions(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        for required in (
            "Crear contacto CRM",
            "Crear seguimiento",
            "Bandeja + CRM",
            "Meta sigue siendo sólo lectura",
            "Bandeja Meta",
            "MKTGAPP_META_",
            "inboxCreateContact",
            "inboxCreateFollowup",
            "inboxApplyCrmMatch",
        ):
            self.assertIn(required, inbox)
        self.assertIn("button.addEventListener('click'", inbox)
        self.assertNotIn("inboxCreateContact(person,kind,item,create);", inbox.split("addEventListener", 1)[0])

    def test_triage_mutations_are_local_crm_only(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        self.assertIn("/contacts`,{method:'POST'", inbox)
        self.assertIn("/activities`,{method:'POST'", inbox)
        self.assertNotIn("/api/inbox/meta`,{method:'POST'", inbox)
        self.assertNotIn("publish-now", inbox)
        self.assertNotIn("sendWhatsApp(", inbox)
        self.assertNotIn("sendEmail(", inbox)
        self.assertNotIn("reply_to", inbox)
        self.assertNotIn("method:'DELETE'", inbox)
        self.assertNotIn("method:'PATCH'", inbox)
        self.assertNotIn("fetch('https://", inbox)

    def test_followup_deduplication_is_local_and_deterministic(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        self.assertIn("inboxInteractionMarker", inbox)
        self.assertIn("activity.contact_id===contact.id", inbox)
        self.assertIn("String(activity.summary||'').includes(marker)", inbox)
        self.assertIn("Ya existe un seguimiento para esta interacción", inbox)
        self.assertIn("inboxState.crmBusy", inbox)

    def test_contact_creation_requires_username_to_avoid_unsafe_duplicate_guessing(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        self.assertIn("if(!companyId||!handle)", inbox)
        self.assertIn("no expone un @usuario suficiente", inbox)
        self.assertIn("contact.instagram||''", inbox)
        self.assertIn("Ese @usuario ya existía en CRM", inbox)

    def test_remote_refresh_remains_explicit_and_read_only_after_wave40(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave39_app.py").read_text(encoding="utf-8")
        self.assertIn("Actualizar desde Meta", inbox)
        self.assertNotIn("inboxRefresh();", inbox)
        self.assertNotIn("setInterval(", inbox)
        self.assertNotIn("MutationObserver", inbox)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)


if __name__ == "__main__":
    unittest.main()
