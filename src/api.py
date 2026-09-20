from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import TradeDatabase
from api_client import OddsAPIClient
from ev_scanner import EVScanner
from scanner import ArbitrageScanner
from matched_betting import MatchedBettingScanner
from fees import win_fee_percentage
from trading_mode import get_trading_mode

socketio = SocketIO(cors_allowed_origins="*")


def create_app(db=None, odds_client=None):
    app = Flask(__name__)
    CORS(app)
    socketio.init_app(app, cors_allowed_origins="*")

    app.config["TRADE_DB"] = db or TradeDatabase()
    app.config["ODDS_CLIENT"] = odds_client or OddsAPIClient(use_mock=False)
    app.config["OPP_CACHE"] = {"ev": None, "arb": None, "mb": None}

    def get_db() -> TradeDatabase:
        return app.config["TRADE_DB"]

    def get_odds() -> OddsAPIClient:
        return app.config["ODDS_CLIENT"]

    def cache():
        return app.config["OPP_CACHE"]

    def wants_refresh() -> bool:
        return request.args.get("refresh", "").lower() in ("1", "true", "yes")

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/system_status", methods=["GET"])
    def get_system_status():
        params = get_db().get_system_params()
        closed_trades = get_db().get_all_closed_trades()
        clv_values = [(t.get("clv_percentage") or 0) for t in closed_trades]
        avg_clv = (sum(clv_values) / len(clv_values)) if clv_values else 0
        perf = get_db().get_performance()
        pending = [
            t for t in get_db().get_all_closed_trades()
            if (t.get("outcome") or "PENDING") == "PENDING"
        ]
        return jsonify({
            "status": "ONLINE",
            "kelly_fraction": params["kelly_fraction"],
            "min_ev_threshold": params["min_ev_threshold"],
            "total_trades": perf["settled_trades"],
            "pending_trades": len(pending),
            "average_clv": avg_clv,
            "realized_pnl": perf["realized_pnl"],
            "bankroll": params.get("bankroll", 1000.0),
            "win_rate": perf["win_rate"],
            "roi": perf["roi"],
            "trading_mode": get_trading_mode(),
            "odds_live": not getattr(get_odds(), "is_mock", True),
            "win_fee_percentage": win_fee_percentage(),
        })

    @app.route("/api/history", methods=["GET"])
    def get_history():
        trades = get_db().get_all_closed_trades()
        trades.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        return jsonify(trades)

    @app.route("/api/broadcast_opportunities", methods=["POST"])
    def broadcast_opportunities():
        data = request.json if isinstance(request.json, list) else []
        cache()["ev"] = data
        socketio.emit("new_opportunities", data)
        return jsonify({"status": "success"})

    @app.route("/api/broadcast_arbitrage", methods=["POST"])
    def broadcast_arbitrage():
        data = request.json if isinstance(request.json, list) else []
        cache()["arb"] = data
        socketio.emit("new_arbitrage", data)
        return jsonify({"status": "success"})

    @app.route("/api/broadcast_matched_betting", methods=["POST"])
    def broadcast_matched_betting():
        data = request.json if isinstance(request.json, list) else []
        cache()["mb"] = data
        socketio.emit("new_matched_bet", data)
        return jsonify({"status": "success"})

    @app.route("/api/opportunities/ev", methods=["GET"])
    def get_ev_opportunities():
        cached = cache()["ev"]
        if cached is not None and not wants_refresh():
            return jsonify(cached)

        params = get_db().get_system_params()
        scanner = EVScanner(get_odds())
        scanner.bankroll = float(get_db().get_system_params().get("bankroll") or 1000.0)
        try:
            opportunities = scanner.scan(
                min_edge=params["min_ev_threshold"],
                kelly_fraction=params["kelly_fraction"],
                fee_percentage=win_fee_percentage(),
            )
            cache()["ev"] = opportunities
            return jsonify(opportunities)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/opportunities/arbitrage", methods=["GET"])
    def get_arbitrage_opportunities():
        cached = cache()["arb"]
        if cached is not None and not wants_refresh():
            return jsonify(cached)

        scanner = ArbitrageScanner(get_odds())
        scanner.investment_amount = 500.0
        try:
            opportunities = scanner.scan()
            cache()["arb"] = opportunities
            return jsonify(opportunities)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/opportunities/matched_betting", methods=["GET"])
    def get_matched_betting_opportunities():
        cached = cache()["mb"]
        if cached is not None and not wants_refresh():
            return jsonify(cached)

        scanner = MatchedBettingScanner(get_odds())
        try:
            opportunities = scanner.find_free_bet_conversions(
                "FanDuel", "DraftKings", free_bet_amount=50.0, min_conversion=0.65
            )
            cache()["mb"] = opportunities
            return jsonify(opportunities)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


app = create_app()


def _maybe_start_embedded_daemon():
    """Free Render web services cannot run a separate worker. Run the loop here."""
    flag = os.environ.get("EMBED_DAEMON", "").lower()
    if flag not in ("1", "true", "yes"):
        return
    if os.environ.get("HYPERION_DAEMON_EMBEDDED") == "1":
        return
    os.environ["HYPERION_DAEMON_EMBEDDED"] = "1"
    import subprocess
    daemon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon.py")
    subprocess.Popen(
        [sys.executable, daemon_path],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    )
    print("Embedded paper daemon started alongside the API.")


_maybe_start_embedded_daemon()

if __name__ == "__main__":
    print("Starting Wealth Generation Backend API on port 5000 with WebSockets...")
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
