import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99ContextualControlHandoffActivityIntegrationTests(unittest.TestCase):
    def test_wave45_open_editor_requires_unique_enabled_canonical_save(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        wave45 = (ROOT / "web" / "followup-reschedule.js").read_text(encoding="utf-8")

        self.assertIn("function controlHandoffSingleGroup", handoff)
        self.assertIn("controls.length===0", handoff)
        self.assertIn("controls.length>1", handoff)
        self.assertIn("controls[0].disabled", handoff)
        self.assertIn(
            "controlHandoffSingleGroup(editors,text=>text==='Guardar fecha'",
            activity,
        )
        self.assertNotIn("controlHandoffSingle(editors,activityRescheduleMeta", activity)
        self.assertIn("Guardar fecha", wave45)
        self.assertIn("save.disabled=true", wave45)
        self.assertIn("save.disabled=false", wave45)

    def test_activity_extension_has_precedence_over_base_activity_fallback(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")

        self.assertIn("targetKind==='ACTIVITY'&&kind==='crm_unscheduled'", handoff)
        self.assertIn("controlHandoffOwnerGap", handoff)
        self.assertIn("const activityRescheduleBaseResolveControl=globalThis.controlHandoffResolveControl", activity)
        self.assertIn("globalThis.controlHandoffResolveControl=function", activity)
        self.assertIn("target_kind||'').toUpperCase()==='ACTIVITY'", activity)
        self.assertIn("crm_unscheduled", activity)
        self.assertIn("pipeline_unscheduled_followup", activity)
        self.assertIn("OPEN_WAVE45_RESCHEDULE", activity)
        self.assertIn("WAVE45_RESCHEDULE_EDITOR", activity)
        self.assertIn("return activityRescheduleBaseResolveControl.apply(this,arguments)", activity)

    def test_decision_group_remains_two_explicit_human_choices(self):
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        self.assertIn("RESOLVE_EXISTING_ACTIVITY", activity)
        self.assertIn("Completar o reprogramar seguimiento", activity)
        self.assertIn("controlHandoffSingle(groups", activity)
        self.assertNotIn("controlHandoffSingleGroup(groups", activity)

    def test_hardening_and_extensions_preserve_exact_semantics(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        opportunity = (ROOT / "web" / "opportunity-followup-control.js").read_text(encoding="utf-8")
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")

        self.assertIn("REQUEST_OPTIONAL_AI_ANALYSIS", handoff)
        self.assertIn("DEFINE_CAMPAIGN_CHANNELS", handoff)
        self.assertIn("No se promueve un control destructivo", handoff)
        self.assertIn("targetKind==='OPPORTUNITY'&&kind.startsWith('pipeline_')", opportunity)
        self.assertIn("No se adivina cuál control corresponde", opportunity)
        self.assertIn("activityRescheduleExactRow(deep.target_id)", activity)
        self.assertIn("La actividad exacta ya no existe", activity)

    def test_docs_describe_terminal_composition_and_frozen_release_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_CONTEXTUAL_CONTROL_HANDOFF.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        expected = (
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → "
            "Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → "
            "Existing Activity Reschedule Control"
        )
        self.assertIn(expected, docs)
        self.assertIn(expected, dev)
        self.assertIn("Opportunity Follow-up Control extension", docs)
        self.assertIn("Existing Activity Reschedule Control extension", docs)
        self.assertIn("Guardar fecha", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)


if __name__ == "__main__":
    unittest.main()
