"""Where the year stands: the four steps, their state, and what to do next."""

from flask import Blueprint, g, jsonify

from core import status
from engine import runner

bp = Blueprint("status", __name__, url_prefix="/api/status")


@bp.get("/<int:tax_year>")
def year_status(tax_year: int):
    # The engine owns what a calculation's inputs are, so it is asked which
    # hashes the current documents would produce; core.status only compares.
    hashes = runner.current_input_hashes(g.user_id, tax_year)
    data = status.build(g.user_id, tax_year, current_hashes=hashes)
    if data is None:
        return jsonify({"error": f"No tax constants for {tax_year}"}), 400
    return jsonify(data)
