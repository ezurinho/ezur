"""El runner mide con los umbrales del bot, no con literales suyos.

Si alguien cambia `config/gates.json`, este test sigue verde y el
comportamiento cambia; si alguien vuelve a escribir 0.20 dentro de
`run_strategy.evaluate`, el test de mutación falla.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import gates as gc
import run_strategy as rs


def _args(*, pbo=0.10, dsr=0.97, t_stat=4.0, ci=(1.2, 2.0), trades=400,
          wfa=40, stress_pf=1.2, plateau=True, alpha=0.05,
          coverage_years=15.0, minbtl_years=10.0):
    spec = {"risk": {"max_mdd_budget": 20.0}, "costs": {"funding": "real_timestamps"}}
    data = {"integrity": {"unexplained_gaps": 0, "duplicates": 0}}
    all_m = {"n": trades, "mdd": -5.0}
    oos_m = {"n": 120, "t_stat": t_stat, "pf_ci95": list(ci)}
    stress = {"pf": stress_pf}
    bench = {"alpha_annual": alpha, "ci95": [alpha - 0.01, alpha + 0.05]}
    validation = {
        "pbo": {"pbo": pbo},
        "dsr": {"dsr": dsr},
        "wfa": {"min_trades_per_fold": wfa},
        "minbtl": {"minbtl_years": minbtl_years},
        "inputs": {"coverage_years": coverage_years},
    }
    return spec, data, all_m, oos_m, stress, {"pass": plateau}, bench, [], validation


class ContractTest(unittest.TestCase):
    def test_el_fichero_canonico_es_el_del_bot(self):
        self.assertTrue(gc.GATES_FILE.is_file(), gc.GATES_FILE)
        self.assertEqual(gc.GATES_FILE.name, "gates.json")
        self.assertEqual(gc.GATES_FILE.parent.name, "config")

    def test_los_constantes_son_las_del_fichero(self):
        doc = json.loads(Path(gc.GATES_FILE).read_text(encoding="utf-8"))["research"]
        self.assertEqual(gc.MAX_PBO, doc["max_pbo"])
        self.assertEqual(gc.MIN_DSR, doc["min_dsr"])
        self.assertEqual(gc.MIN_OOS_T_STAT, doc["min_oos_t_stat"])
        self.assertEqual(gc.MIN_OOS_PF_CI_LOW, doc["min_oos_pf_ci_low"])
        self.assertEqual(gc.MIN_TRADES, doc["min_trades"])
        self.assertEqual(gc.MIN_WFA_TRADES_PER_FOLD, doc["min_wfa_trades_per_fold"])
        self.assertEqual(gc.MIN_MINBTL_COVERAGE, doc["min_minbtl_coverage"])
        self.assertEqual(gc.COST_STRESS_MULTIPLIER, doc["cost_stress_multiplier"])
        self.assertEqual(gc.MIN_COST_STRESS_PF, doc["min_cost_stress_pf"])
        self.assertEqual(gc.MIN_PLATEAU_PF, doc["min_plateau_pf"])
        self.assertEqual(gc.MIN_BENCHMARK_ALPHA_CI_LOW, doc["min_benchmark_alpha_ci_low"])
        self.assertEqual(gc.MAX_UNEXPLAINED_GAPS, doc["max_unexplained_gaps"])

    def test_una_spec_que_pasa_todo_se_aprueba(self):
        _, _, verdict = rs.evaluate(*_args())
        self.assertEqual(verdict, "APPROVED")

    def test_pbo_por_encima_del_umbral_rechaza(self):
        _, failed, verdict = rs.evaluate(*_args(pbo=gc.MAX_PBO + 0.01))
        self.assertEqual(verdict, "REJECTED")
        self.assertIn("pbo", failed)

    def test_si_el_contrato_cambia_el_runner_obedece(self):
        """La prueba de que no hay un 0.20 escondido en el código."""
        pbo = gc.MAX_PBO + 0.01
        _, failed, verdict = rs.evaluate(*_args(pbo=pbo))
        self.assertEqual(verdict, "REJECTED")

        with mock.patch.object(gc, "MAX_PBO", pbo + 0.05):
            _, failed, verdict = rs.evaluate(*_args(pbo=pbo))
        self.assertEqual(verdict, "APPROVED")
        self.assertNotIn("pbo", failed)

    def test_menos_operaciones_del_contrato_es_inconcluso(self):
        # `trades` es puerta blanda: no rechaza, pero impide aprobar.
        gates, _, verdict = rs.evaluate(*_args(trades=gc.MIN_TRADES - 50))
        self.assertEqual(verdict, "INCONCLUSIVE")
        self.assertIs(gates["trades"]["pass"], False)

    def test_dsr_bajo_el_umbral_rechaza(self):
        _, failed, verdict = rs.evaluate(*_args(dsr=gc.MIN_DSR - 0.05))
        self.assertEqual(verdict, "REJECTED")
        self.assertIn("dsr", failed)

    def test_el_stress_de_costes_usa_el_multiplicador_del_fichero(self):
        self.assertEqual(rs.STRESS_MULT, gc.COST_STRESS_MULTIPLIER)
        _, failed, verdict = rs.evaluate(*_args(stress_pf=gc.MIN_COST_STRESS_PF - 0.1))
        self.assertEqual(verdict, "REJECTED")
        self.assertIn("cost_stress_2x", failed)

    def test_minbtl_sin_cobertura_suficiente_es_inconcluso(self):
        # 6,8 años disponibles frente a 14,55 que pide el Sharpe: no hay historia.
        gates, _, verdict = rs.evaluate(*_args(coverage_years=6.8, minbtl_years=14.55))
        self.assertEqual(verdict, "INCONCLUSIVE")
        self.assertIs(gates["minbtl"]["pass"], False)
        self.assertAlmostEqual(gates["minbtl"]["value"], 0.467, places=2)

    def test_minbtl_obedece_al_contrato(self):
        with mock.patch.object(gc, "MIN_MINBTL_COVERAGE", 0.4):
            gates, _, verdict = rs.evaluate(*_args(coverage_years=6.8, minbtl_years=14.55))
        self.assertEqual(verdict, "APPROVED")
        self.assertIs(gates["minbtl"]["pass"], True)

    def test_sin_fichero_falla_con_mensaje_util(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            gc.load("C:/no/existe/gates.json")
        self.assertIn("contrato de umbrales", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
