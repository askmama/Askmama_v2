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
    new_qty = max(0, cur_qty - quantity) if action == "taken" else cur_qty + quantity
    new_status = _compute_status(new_qty, item['min_qty'])
    now = datetime.now()

    # Update Inventory row
    ws_inv.update_cell(found_row, COL_QTY, new_qty)
    ws_inv.update_cell(found_row, COL_STATUS, new_status)
    ws_inv.update_cell(found_row, COL_LAST_UPDATED, now.strftime("%d %b %Y"))
    ws_inv.format(f'I{found_row}', {'horizontalAlignment': 'CENTER'})

    # Append to Transaction Log
    ws_log.append_row([
        now.strftime("%d %b %Y %H:%M"),
        item['id'],
        item['name'],
        action.upper(),
        quantity,
        raw_command,
        new_qty,
    ])

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
        ws_inv.format(f'I{totals_row}', {'horizontalAlignment': 'CENTER'})
    else:
        ws_inv.append_row(new_row_data)
        last_row = len(ws_inv.get_all_values())
        ws_inv.format(f'I{last_row}', {'horizontalAlignment': 'CENTER'})
    ws_log.append_row([
        now.strftime("%d %b %Y %H:%M"),
        '',
        item_name,
        action.upper(),
        quantity,
        raw_command,
        new_qty,
    ])

    return {
        'name':     item_name,
        'prev_qty': 0,
        'new_qty':  new_qty,
        'status':   new_status,
        'action':   action,
        'quantity': quantity,
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
    }
