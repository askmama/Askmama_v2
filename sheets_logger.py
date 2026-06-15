"""
Google Sheets inventory manager.
Handles item lookups, stock updates, and transaction logging.
"""
import os
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Inventory sheet column positions (1-based, matching Excel structure)
INV_START_ROW = 4   # Data rows begin here
COL_ID = 1          # A: item ID
COL_NAME = 2        # B: item name
COL_CATEGORY = 3    # C: category
COL_QTY = 4         # D: current quantity
COL_MIN_QTY = 5     # E: minimum quantity threshold
COL_MAX_QTY = 6     # F: maximum quantity
COL_UNIT = 7        # G: unit
COL_STATUS = 8      # H: status (OK / LOW STOCK / MISSING)
COL_LAST_UPDATED = 9  # I: last updated date

CATEGORY_PREFIX = {
    'salon': 'S',
    'cleaning': 'C',
    'medical': 'M',
    'office': 'O',
}

# Transaction Log formatting — must match the layout set by format_sheets.py
_LOG_HEADER_ROW = 2   # 1-based row where Transaction Log headers live
_LOG_N_COLS = 7
_LOG_ACTION_COL = 3   # 0-indexed column D
_LOG_CENTRE_COLS = [1, 4, 6]  # Item ID (B), Qty (E), New Stock Level (G)


def _rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


_LOG_ROW_COLORS = {
    'ADDED': _rgb(198, 239, 206),
    'TAKEN': _rgb(255, 199, 206),
    'alt':   _rgb(245, 247, 250),
    'white': _rgb(255, 255, 255),
}

_OUTER_BORDER = {"style": "SOLID_MEDIUM", "width": 2, "color": _rgb(30, 100, 82)}
_INNER_BORDER = {"style": "SOLID", "width": 1, "color": _rgb(189, 195, 199)}

# Keep aliases so existing references in _format_log_row continue to work
_LOG_OUTER_BORDER = _OUTER_BORDER
_LOG_INNER_BORDER = _INNER_BORDER

# Inventory sheet formatting constants
_INV_N_COLS = 10         # A–J (Item ID … Notes)
_INV_STATUS_COL = 7      # 0-indexed column H
_INV_CENTRE_COLS = [0, 3, 4, 5, 6, 8]  # ID(A) Qty(D) Min(E) Max(F) Unit(G) Date(I)

_INV_STATUS_COLORS = {
    'OK':        _rgb(198, 239, 206),
    'LOW STOCK': _rgb(255, 235, 156),
    'MISSING':   _rgb(255, 199, 206),
}
_INV_ALT_BG  = _rgb(245, 247, 250)
_INV_WHITE   = _rgb(255, 255, 255)


def _format_inv_row(ws, row_1based, status):
    """Apply background, status colour, alignment, and borders to a new inventory row."""
    if not row_1based:
        return
    sid = ws.id
    r = row_1based - 1                      # 0-indexed
    data_start = INV_START_ROW - 1          # 0-indexed (= 3)
    is_alt = (r - data_start) % 2 == 1
    row_bg = _INV_ALT_BG if is_alt else _INV_WHITE
    status_bg = _INV_STATUS_COLORS.get((status or '').upper(), row_bg)
    is_alert = (status or '').upper() in ('LOW STOCK', 'MISSING')

    def rng(r1, r2, c1, c2):
        return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2}

    requests = [
        # Row background
        {"repeatCell": {
            "range": rng(r, r + 1, 0, _INV_N_COLS),
            "cell": {"userEnteredFormat": {"backgroundColor": row_bg}},
            "fields": "userEnteredFormat.backgroundColor",
        }},
        # Status cell: colour + conditional bold + centred
        {"repeatCell": {
            "range": rng(r, r + 1, _INV_STATUS_COL, _INV_STATUS_COL + 1),
            "cell": {"userEnteredFormat": {
                "backgroundColor": status_bg,
                "textFormat": {"bold": is_alert},
                "horizontalAlignment": "CENTER",
            }},
            "fields": ("userEnteredFormat.backgroundColor,"
                       "userEnteredFormat.textFormat.bold,"
                       "userEnteredFormat.horizontalAlignment"),
        }},
        # Centre-align numeric / date columns
        *[{"repeatCell": {
            "range": rng(r, r + 1, c, c + 1),
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }} for c in _INV_CENTRE_COLS],
        # Previous last data row: soften bottom border to thin
        *([{"updateBorders": {
            "range": rng(r - 1, r, 0, _INV_N_COLS),
            "bottom": _INNER_BORDER,
        }}] if r > data_start else []),
        # New row: thick outer borders, thin inner column dividers
        {"updateBorders": {
            "range": rng(r, r + 1, 0, _INV_N_COLS),
            "top": _INNER_BORDER,
            "bottom": _OUTER_BORDER,
            "left": _OUTER_BORDER,
            "right": _OUTER_BORDER,
            "innerVertical": _INNER_BORDER,
        }},
    ]
    ws.spreadsheet.batch_update({"requests": requests})


def _parse_appended_row(resp):
    """Return the 1-based row number from an append_row() API response."""
    range_str = (resp or {}).get('updates', {}).get('updatedRange', '')
    if range_str:
        last_cell = range_str.split(':')[-1]          # e.g. "G45"
        digits = ''.join(c for c in last_cell if c.isdigit())
        if digits:
            return int(digits)
    return None


def _format_log_row(ws, row_1based, action):
    """Apply background, action colour, alignment, and borders to a new log row."""
    if not row_1based:
        return
    sid = ws.id
    r = row_1based - 1  # 0-indexed
    is_alt = (r - _LOG_HEADER_ROW) % 2 == 1
    row_bg = _LOG_ROW_COLORS['alt'] if is_alt else _LOG_ROW_COLORS['white']
    action_bg = _LOG_ROW_COLORS.get(action.upper(), row_bg)

    def rng(r1, r2, c1, c2):
        return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2}

    requests = [
        # Row background
        {"repeatCell": {
            "range": rng(r, r + 1, 0, _LOG_N_COLS),
            "cell": {"userEnteredFormat": {"backgroundColor": row_bg}},
            "fields": "userEnteredFormat.backgroundColor",
        }},
        # Action cell: colour + bold + centred
        {"repeatCell": {
            "range": rng(r, r + 1, _LOG_ACTION_COL, _LOG_ACTION_COL + 1),
            "cell": {"userEnteredFormat": {
                "backgroundColor": action_bg,
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": ("userEnteredFormat.backgroundColor,"
                       "userEnteredFormat.textFormat.bold,"
                       "userEnteredFormat.horizontalAlignment"),
        }},
        # Centre-align other columns
        *[{"repeatCell": {
            "range": rng(r, r + 1, c, c + 1),
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }} for c in _LOG_CENTRE_COLS],
        # Previous last row: soften its bottom border to thin
        *([{"updateBorders": {
            "range": rng(r - 1, r, 0, _LOG_N_COLS),
            "bottom": _LOG_INNER_BORDER,
        }}] if r > _LOG_HEADER_ROW else []),
        # New row: full border — thick on left/right/bottom, thin on top and inner columns
        {"updateBorders": {
            "range": rng(r, r + 1, 0, _LOG_N_COLS),
            "top": _LOG_INNER_BORDER,
            "bottom": _LOG_OUTER_BORDER,
            "left": _LOG_OUTER_BORDER,
            "right": _LOG_OUTER_BORDER,
            "innerVertical": _LOG_INNER_BORDER,
        }},
    ]
    ws.spreadsheet.batch_update({"requests": requests})


def _get_client():
    creds_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_worksheets():
    sheet_name = os.getenv('GOOGLE_SHEET_NAME')
    if not sheet_name:
        raise ValueError("GOOGLE_SHEET_NAME not set in environment")
    client = _get_client()
    gsheet = client.open(sheet_name)
    return gsheet.worksheet("Inventory"), gsheet.worksheet("Transaction Log")


def _safe_int(value, default=0):
    try:
        return int(float(str(value))) if value not in ('', None) else default
    except (ValueError, TypeError):
        return default


def _compute_status(qty, min_qty):
    if qty == 0:
        return "MISSING"
    if qty <= min_qty:
        return "LOW STOCK"
    return "OK"


def _name_matches(parsed_name, sheet_name):
    """
    Flexible bidirectional partial match.
    Either the parsed name is in the sheet name, or vice versa.
    """
    a = parsed_name.lower().strip()
    b = sheet_name.lower().strip()
    return a in b or b in a


def find_item(item_name):
    """
    Search Inventory tab for an item by partial name match.
    Returns (row_index_1based, item_dict) or (None, None) if not found.
    """
    ws_inv, _ = _get_worksheets()
    all_rows = ws_inv.get_all_values()

    logger.info(f"Searching for item: '{item_name}' — sheet has {len(all_rows)} rows")
    for i, row in enumerate(all_rows):
        if i < INV_START_ROW - 1:
            continue
        name_cell = row[COL_NAME - 1] if len(row) >= COL_NAME else ''
        if name_cell:
            logger.info(f"  Row {i+1}: '{name_cell}'")
        if name_cell and _name_matches(item_name, name_cell):
            row_1based = i + 1
            return row_1based, {
                'id':      row[COL_ID - 1] if len(row) >= COL_ID else '',
                'name':    name_cell,
                'qty':     _safe_int(row[COL_QTY - 1] if len(row) >= COL_QTY else 0),
                'min_qty': _safe_int(row[COL_MIN_QTY - 1] if len(row) >= COL_MIN_QTY else 0),
            }
    logger.info(f"  No match found for '{item_name}'")
    return None, None


def update_inventory(item_name, quantity, action, raw_command):
    """
    Update stock for an existing item in the Inventory tab.
    Returns result dict, or None if item not found.
    """
    ws_inv, ws_log = _get_worksheets()
    all_rows = ws_inv.get_all_values()

    # Find item row
    found_row = None
    item = None
    for i, row in enumerate(all_rows):
        if i < INV_START_ROW - 1:
            continue
        name_cell = row[COL_NAME - 1] if len(row) >= COL_NAME else ''
        if name_cell and _name_matches(item_name, name_cell):
            found_row = i + 1
            item = {
                'id':      row[COL_ID - 1] if len(row) >= COL_ID else '',
                'name':    name_cell,
                'qty':     _safe_int(row[COL_QTY - 1] if len(row) >= COL_QTY else 0),
                'min_qty': _safe_int(row[COL_MIN_QTY - 1] if len(row) >= COL_MIN_QTY else 0),
            }
            break

    if not found_row:
        return None

    cur_qty = item['qty']
    if action == "taken" and quantity > cur_qty:
        raise ValueError(
            f"Cannot deduct {quantity} — only {cur_qty} {item['name']} in stock."
        )
    new_qty = cur_qty - quantity if action == "taken" else cur_qty + quantity
    new_status = _compute_status(new_qty, item['min_qty'])
    now = datetime.now()

    # Update Inventory row — RAW keeps numbers as integers and date as text,
    # preventing gspread 6's user_entered from converting the date string to a serial number.
    now_str = now.strftime("%d %b %Y")
    ws_inv.batch_update(
        [
            {'range': f'D{found_row}', 'values': [[int(new_qty)]]},
            {'range': f'H{found_row}', 'values': [[new_status]]},
            {'range': f'I{found_row}', 'values': [[now_str]]},
        ],
        value_input_option='RAW',
    )
    # Apply consistent cell format to match original data: qty as plain integer,
    # date center-aligned as text.
    ws_inv.batch_format(
        [
            {
                'range': f'D{found_row}',
                'format': {'numberFormat': {'type': 'NUMBER', 'pattern': '0'}},
            },
            {
                'range': f'I{found_row}',
                'format': {'horizontalAlignment': 'CENTER'},
            },
        ]
    )

    # Append to Transaction Log
    resp = ws_log.append_row([
        now.strftime("%d %b %Y %H:%M"),
        item['id'],
        item['name'],
        action.upper(),
        quantity,
        raw_command,
        new_qty,
    ])
    _format_log_row(ws_log, _parse_appended_row(resp), action)

    return {
        'name':     item['name'],
        'prev_qty': cur_qty,
        'new_qty':  new_qty,
        'status':   new_status,
        'action':   action,
        'quantity': quantity,
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _find_totals_row(all_rows):
    """Return the 1-based row index of the TOTALS row from pre-fetched rows, or None."""
    for i, row in enumerate(all_rows):
        col_a = str(row[0]).strip().upper() if len(row) > 0 else ''
        col_b = str(row[1]).strip().upper() if len(row) > 1 else ''
        if 'TOTALS' in col_a or 'TOTALS' in col_b:
            return i + 1  # 1-based
    return None


def _generate_item_id(all_rows, category):
    """Auto-generate the next item ID for the given category (e.g. S009, C004)."""
    prefix = CATEGORY_PREFIX.get((category or '').lower(), 'X')
    max_num = 0
    for row in all_rows:
        cell_id = str(row[COL_ID - 1]).strip() if len(row) >= COL_ID else ''
        if cell_id.upper().startswith(prefix) and cell_id[1:].isdigit():
            max_num = max(max_num, int(cell_id[1:]))
    return f"{prefix}{max_num + 1:03d}"


def append_new_item(item_name, quantity, action, raw_command,
                    category='', unit='', min_qty=0, max_qty=''):
    """
    Add a brand-new item to the Inventory tab above the TOTALS row, and log the transaction.
    Returns result dict.
    """
    ws_inv, ws_log = _get_worksheets()
    now = datetime.now()
    all_rows = ws_inv.get_all_values()

    min_qty_int = _safe_int(min_qty)
    new_qty = quantity if action == "added" else max(0, -quantity)
    new_status = _compute_status(new_qty, min_qty_int)
    item_id = _generate_item_id(all_rows, category)

    totals_row = _find_totals_row(all_rows)
    new_row_data = [
        item_id, item_name, category, new_qty,
        min_qty_int, max_qty, unit, new_status, now.strftime("%d %b %Y"),
    ]

    if totals_row:
        ws_inv.insert_row(new_row_data, index=totals_row)
        _format_inv_row(ws_inv, totals_row, new_status)
    else:
        ws_inv.append_row(new_row_data)
        last_row = len(ws_inv.get_all_values())
        _format_inv_row(ws_inv, last_row, new_status)
    resp = ws_log.append_row([
        now.strftime("%d %b %Y %H:%M"),
        '',
        item_name,
        action.upper(),
        quantity,
        raw_command,
        new_qty,
    ])
    _format_log_row(ws_log, _parse_appended_row(resp), action)

    return {
        'name':     item_name,
        'prev_qty': 0,
        'new_qty':  new_qty,
        'status':   new_status,
        'action':   action,
        'quantity': quantity,
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
    }
