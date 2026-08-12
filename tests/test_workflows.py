import unittest

from binario_marketing.workflows import Recipe, WorkflowEngine


class WorkflowTests(unittest.TestCase):
    def test_recipe_is_deterministic_and_traced(self):
        engine = WorkflowEngine({
            "validate": lambda state: state | {"validated": True},
            "score": lambda state: state | {"score": 1.0},
        })
        result = engine.run(Recipe("demo", ("validate", "score")), {"input": "x"})
        self.assertTrue(result["validated"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual([row["step"] for row in result["_trace"]], ["validate", "score"])


if __name__ == "__main__":
    unittest.main()
