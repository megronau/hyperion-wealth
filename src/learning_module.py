from database import TradeDatabase


class LearningModule:
    def __init__(self, db_path: str = None):
        self.db = TradeDatabase(db_path)

        self.MAX_KELLY = 0.50
        self.MIN_KELLY = 0.05
        self.MIN_EV_THRESHOLD_FLOOR = 0.01
        self.MAX_EV_THRESHOLD_CEIL = 0.05
        self.MIN_SETTLED = 15

    def evaluate_performance(self):
        """Size risk off realized ROI, not simulated closing-line noise."""
        stats = self.db.get_performance()
        if stats["settled_trades"] < self.MIN_SETTLED:
            print(f"Not enough settled trades to learn ({stats['settled_trades']}).")
            return

        roi = stats["roi"]
        pnl = stats["realized_pnl"]
        print(
            f"Evaluated {stats['settled_trades']} settled trades. "
            f"ROI {roi*100:.2f}% | P&L ${pnl:.2f}"
        )

        params = self.db.get_system_params()
        current_kelly = params["kelly_fraction"]
        current_min_ev = params["min_ev_threshold"]
        new_kelly = current_kelly
        new_min_ev = current_min_ev

        if roi > 0.02 and pnl > 0:
            new_kelly = min(self.MAX_KELLY, current_kelly + 0.02)
            new_min_ev = max(self.MIN_EV_THRESHOLD_FLOOR, current_min_ev - 0.002)
            print("PERFORMANCE PROFITABLE: Slightly increasing volume.")
        elif roi < 0 or pnl < 0:
            new_kelly = max(self.MIN_KELLY, current_kelly - 0.10)
            new_min_ev = min(self.MAX_EV_THRESHOLD_CEIL, current_min_ev + 0.01)
            print("PERFORMANCE LOSING: Cutting stake size and demanding more edge.")
        else:
            print("PERFORMANCE FLAT: Holding parameters.")

        if new_kelly != current_kelly or new_min_ev != current_min_ev:
            self.db.update_system_params(new_min_ev, new_kelly)
            print(f"Updated System Params -> Kelly: {new_kelly:.2f}, Min EV: {new_min_ev*100:.2f}%")
        else:
            print("No parameter adjustments deemed necessary.")


if __name__ == "__main__":
    print("Initializing Learning Module...")
    learner = LearningModule("test_brain.db")
    learner.evaluate_performance()
