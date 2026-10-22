"""Замены: сотрудник просит коллегу, коллега соглашается, управляющий утверждает."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..constants import ACTIVE_REQUEST_STATUSES
from ..db import get_db
from ..logic import swaps
from ..logic.users import colleagues_of
from ..security import is_safe_next, login_required, role_required
from . import flash_errors

bp = Blueprint("swaps", __name__, url_prefix="/requests")

MANAGER_TABS = (
    ("pending_manager", "Ждут решения"),
    ("pending_colleague", "Ждут коллегу"),
    ("closed", "Архив"),
    ("all", "Все"),
)
TAB_CONDITIONS = {
    "pending_manager": "r.status = 'pending_manager'",
    "pending_colleague": "r.status = 'pending_colleague'",
    "closed": "r.status IN ('approved', 'rejected', 'declined', 'cancelled')",
    "all": "",
}

# действие -> (роль, поле запроса с владельцем действия, статусы, из которых оно доступно)
ACTIONS = {
    "accept": ("employee", "to_user_id", ("pending_colleague",)),
    "decline": ("employee", "to_user_id", ("pending_colleague",)),
    "cancel": ("employee", "from_user_id", ACTIVE_REQUEST_STATUSES),
    "approve": ("manager", None, ("pending_manager",)),
    "reject": ("manager", None, ACTIVE_REQUEST_STATUSES),
}
# действие -> (новый статус, сообщение, категория flash)
SIMPLE_RESULTS = {
    "accept": ("pending_manager", "Вы согласились на замену. Осталось решение управляющего.", "success"),
    "decline": ("declined", "Вы отказались от замены.", "info"),
    "cancel": ("cancelled", "Запрос отменён.", "info"),
    "reject": ("rejected", "Замена отклонена.", "info"),
}


@bp.route("")
@login_required
def index():
    db = get_db()
    if g.user["role"] == "manager":
        tab = request.args.get("tab", "pending_manager")
        if tab not in TAB_CONDITIONS:
            tab = "pending_manager"
        return render_template("swaps/manager.html", tabs=MANAGER_TABS, tab=tab,
                               items=swaps.list_requests(db, TAB_CONDITIONS[tab]))

    user_id = g.user["id"]
    return render_template(
        "swaps/employee.html",
        my_shifts=swaps.requestable_shifts(db, user_id),
        colleagues=colleagues_of(db, user_id),
        incoming=swaps.list_requests(db, "r.to_user_id = ?", (user_id,)),
        outgoing=swaps.list_requests(db, "r.from_user_id = ?", (user_id,)),
        selected_shift=request.args.get("shift", type=int),
        selected_colleague=request.args.get("to", type=int),
    )


@bp.route("", methods=["POST"])
@role_required("employee")
def create():
    db = get_db()
    data, errors = swaps.validate_new_request(db, g.user["id"], request.form)
    if errors:
        flash_errors(errors)
        return redirect(url_for("swaps.index", shift=data["shift_id"], to=data["to_user_id"]))
    swaps.create_request(db, g.user["id"], data)
    flash("Запрос отправлен коллеге. После его согласия решение примет управляющий.", "success")
    return redirect(url_for("swaps.index"))


@bp.route("/<int:request_id>/<action>", methods=["POST"])
@login_required
def act(request_id, action):
    if action not in ACTIONS:
        abort(404)
    role, owner_field, allowed_statuses = ACTIONS[action]
    db = get_db()
    req = swaps.get_request(db, request_id) or abort(404)
    if g.user["role"] != role or (owner_field and req[owner_field] != g.user["id"]):
        abort(403)

    back = request.form.get("next", "")
    back_url = back if is_safe_next(back) else url_for("swaps.index")
    if req["status"] not in allowed_statuses:
        flash("Этот запрос уже обработан или находится на другом этапе.", "warning")
        return redirect(back_url)

    if action in ("accept", "approve"):
        problem = swaps.shift_problem(db, req["shift_id"], req["from_user_id"], req["to_user_id"])
        if problem:
            flash(f"Замена невозможна: {problem}", "danger")
            return redirect(back_url)

    if action == "approve":
        swaps.approve(db, req)
        flash("Замена одобрена — смена передана коллеге.", "success")
    else:
        status, message, category = SIMPLE_RESULTS[action]
        swaps.set_status(db, request_id, status)
        flash(message, category)
    return redirect(back_url)
