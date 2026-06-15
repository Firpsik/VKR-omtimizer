import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.optimizer_service import (
    AdapterError,
    add_sales_observations,
    delete_product,
    delete_sales,
    get_all_results,
    get_orphan_products,
    get_references,
    get_sales_history,
    list_all_products,
    list_canonical_categories_full,
    list_canonical_groups,
    optimize_single_product,
    recompute_optimization,
    upload_marketplace_report,
)
from src.auth import (
    COOKIE_MAX_AGE,
    SESSION_COOKIE,
    create_user,
    delete_user,
    find_user_by_email,
    get_current_user,
    make_session_token,
    require_user,
    require_writeable_user,
    verify_password,
)
from src.etl.sales_adapters import AdapterError

app = FastAPI(title="АСМП-Маркет — система мониторинга продаж на маркетплейсах")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _render_index(request: Request, user: dict, message: str | None = None):
    refs = get_references()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "categories": refs["categories"],
            "results": get_all_results(user["user_id"]),
            "orphans": get_orphan_products(user["user_id"]),
            "all_products": list_all_products(user["user_id"]),
            "message": message,
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return _render_index(request, user)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    if get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": error},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = find_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"error": "Неверный email или пароль"},
            status_code=401,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, make_session_token(user["user_id"]),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request=request, name="register.html",
        context={"error": error},
    )


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    display_name: str = Form(""),
):
    if password != password2:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Пароли не совпадают"},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Пароль должен быть не короче 6 символов"},
            status_code=400,
        )
    try:
        uid = create_user(email, password, display_name or None)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": str(e)},
            status_code=400,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, make_session_token(uid),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/account/delete")
async def account_delete(user: dict = Depends(require_writeable_user)):
    delete_user(user["user_id"])
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/demo")
async def demo_login():
    user = find_user_by_email("demo@mail.ru")
    if not user:
        return JSONResponse({"error": "demo не настроен"}, status_code=500)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, make_session_token(user["user_id"]),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return response


@app.post("/optimize", response_class=HTMLResponse)
async def run_optimization(
    request: Request,
    sku: str = Form(...),
    name: str = Form(...),
    category_code: str = Form(...),
    weight_kg: float = Form(...),
    volume_l: float = Form(...),
    cost_rub: float = Form(...),
    promo_rub: float = Form(0.0),
    stock_qty: int | None = Form(None),
    override_marketplace_code: str = Form("wb"),
    return_rate_override: float = Form(None),
    storage_days_override: int = Form(None),
    ktr_override: float = Form(None),
    kwh_override: float = Form(None),
    promo_pct_override: float = Form(None),
    packaging_fee_override: float = Form(None),
    cofinance_pct_override: float = Form(None),
    user: dict = Depends(require_writeable_user),
):
    overrides = {}
    mp_code = (override_marketplace_code or "wb").strip().lower()
    if return_rate_override is not None:
        overrides["return_rate"] = return_rate_override / 100.0
    if storage_days_override is not None:
        overrides["storage_days"] = storage_days_override
    if mp_code == "wb" and ktr_override is not None:
        overrides["ktr"] = ktr_override
    if mp_code == "wb" and kwh_override is not None:
        overrides["kwh"] = kwh_override
    if promo_pct_override is not None:
        overrides["promo_pct"] = promo_pct_override / 100.0
    if mp_code == "ym" and packaging_fee_override is not None:
        overrides["packaging_fee_rub"] = packaging_fee_override
    if mp_code == "ym" and cofinance_pct_override is not None:
        overrides["cofinance_pct"] = cofinance_pct_override / 100.0
    try:
        result = optimize_single_product(
            sku=sku, name=name, category_code=category_code,
            weight_kg=weight_kg, volume_l=volume_l,
            cost_rub=cost_rub, promo_rub=promo_rub,
            user_id=user["user_id"],
            overrides=overrides or None,
            override_marketplace_code=mp_code,
            stock_qty_limit=stock_qty,
        )
        if result["n_feasible"] == 0:
            message = (
                f"Добавлен товар {sku} ({name}). Истории продаж недостаточно — "
                "загрузите CSV-отчёт из ЛК площадки."
            )
        else:
            message = (
                f"Расчёт по {sku}: ★ лучшая площадка — {result['best_marketplace']} "
                f"(прибыль {result['best_profit']:,.0f} ₽)"
            )
    except Exception as e:
        message = f"Ошибка: {e}"
    return _render_index(request, user, message)


@app.post("/delete", response_class=HTMLResponse)
async def remove_product(
    request: Request, sku: str = Form(...),
    user: dict = Depends(require_writeable_user),
):
    res = delete_product(sku, user["user_id"])
    message = (f"Товар {sku} удалён" if res["deleted"]
               else f"Товар {sku} не найден")
    return _render_index(request, user, message)


@app.get("/api/products")
async def api_products(user: dict = Depends(require_user)):
    return list_all_products(user["user_id"])


@app.get("/api/results")
async def api_results(user: dict = Depends(require_user)):
    return get_all_results(user["user_id"])


@app.get("/api/canonical-groups")
async def api_canonical_groups(_user: dict = Depends(require_user)):
    return list_canonical_groups()


@app.get("/api/canonical-categories")
async def api_canonical_categories(_user: dict = Depends(require_user)):
    return list_canonical_categories_full()


@app.post("/sales/upload-mp-report", response_class=HTMLResponse)
async def upload_mp_report_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    marketplace_code: str | None = Form(None),
    sku_override: str | None = Form(None),
    replace: bool = Form(False),
    user: dict = Depends(require_writeable_user),
):
    MP_NAME = {"wb": "WB", "ozon": "Ozon", "ym": "ЯМ"}
    parts, errors = [], []
    for upload in files:
        try:
            raw = await upload.read()
            try:
                csv_text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                csv_text = raw.decode("cp1251")
            result = upload_marketplace_report(
                csv_text=csv_text,
                user_id=user["user_id"],
                marketplace_code=marketplace_code or None,
                sku_override=sku_override or None,
                replace=replace,
            )
            mp = MP_NAME.get(result["marketplace_code"], result["marketplace_code"])
            inserted = result["inserted"]
            skipped = result.get("skipped_unknown_sku", 0)
            sku_list = ", ".join(result["by_sku"].keys()) or "—"
            if inserted:
                parts.append(f"✓ {mp} +{inserted} → {sku_list}")
            elif skipped:
                parts.append(
                    f"⚠ {mp}: SKU не найден ({skipped} строк) — "
                    f"создайте товар с тем же SKU и повторите"
                )
            else:
                parts.append(f"⚠ {mp}: ни одной строки не загружено")
        except AdapterError as e:
            errors.append(f"{upload.filename}: {e}")
        except Exception as e:
            errors.append(f"{upload.filename}: ошибка — {e}")
    message = " | ".join(parts)
    if errors:
        message = (message + "  ⚠ " if message else "⚠ ") + "; ".join(errors)
    if not message:
        message = "—"
    return _render_index(request, user, message)


@app.post("/sales/add")
async def add_sales(payload: dict, user: dict = Depends(require_writeable_user)):
    try:
        result = add_sales_observations(
            sku=payload["sku"],
            marketplace_code=payload["marketplace_code"],
            observations=payload.get("observations", []),
            user_id=user["user_id"],
            replace=payload.get("replace", False),
        )
        try:
            rec = recompute_optimization(payload["sku"], user["user_id"])
            result["recompute"] = {
                "best_marketplace": rec["best_marketplace"],
                "best_profit": rec["best_profit"],
            }
        except Exception:
            pass
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/sales/clear", response_class=HTMLResponse)
async def clear_sales(
    request: Request,
    sku: str = Form(...),
    marketplace_code: str = Form(""),
    user: dict = Depends(require_writeable_user),
):
    try:
        mp = marketplace_code or None
        result = delete_sales(sku, user["user_id"], marketplace_code=mp)
        if mp:
            message = f"Удалены продажи {sku} / {mp}: {result['deleted']} строк"
        else:
            message = f"Удалены все продажи {sku}: {result['deleted']} строк (по всем площадкам)"
    except ValueError as e:
        message = f"Ошибка: {e}"
    except Exception as e:
        message = f"Ошибка: {e}"
    return _render_index(request, user, message)


@app.get("/api/sales/{sku}")
async def api_sales(
    sku: str, marketplace_code: str | None = None,
    user: dict = Depends(require_user),
):
    try:
        return get_sales_history(sku, user["user_id"], marketplace_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)