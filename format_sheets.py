"""
Apply visual formatting to the AskMama Google Sheets spreadsheet.
Run once to improve table readability — safe to re-run.
"""
import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
SPREADSHEET_ID = '1L8HsraKHcaEa61mXrjgpWMfNUtkJYcJlyRoz9sbiwJw'


def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


C = {
    'header_bg':    rgb(30, 100, 82),    # deep teal
    'header_text':  rgb(255, 255, 255),  # white
    'ok':           rgb(198, 239, 206),  # soft green
    'low_stock':    rgb(255, 235, 156),  # soft amber
    'missing':      rgb(255, 199, 206),  # soft red
    'added':        rgb(198, 239, 206),  # soft green
    'taken':        rgb(255, 199, 206),  # soft red
    'alt_row':      rgb(245, 247, 250),  # very light blue-grey
    'border':       rgb(189, 195, 199),  # light grey
    'title_bg':     rgb(44, 62, 80),     # dark navy for title
    'title_text':   rgb(255, 255, 255),
}

THIN_BORDER = {"style": "SOLID", "width": 1, "color": C['border']}
THICK_BORDER = {"style": "SOLID_MEDIUM", "width": 2, "color": rgb(30, 100, 82)}


def _range(sheet_id, r1, r2, c1, c2):
    return {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
            "startColumnIndex": c1, "endColumnIndex": c2}


def fmt_request(sheet_id, r1, r2, c1, c2, **kwargs):
    cell_fmt = {}
    field_paths = []

    if 'bg' in kwargs:
        cell_fmt['backgroundColor'] = kwargs['bg']
        field_paths.append('userEnteredFormat.backgroundColor')

    tf = {}
    if 'color' in kwargs:
        tf['foregroundColor'] = kwargs['color']
        field_paths.append('userEnteredFormat.textFormat.foregroundColor')
    if 'bold' in kwargs:
        tf['bold'] = kwargs['bold']
        field_paths.append('userEnteredFormat.textFormat.bold')
    if 'size' in kwargs:
        tf['fontSize'] = kwargs['size']
        field_paths.append('userEnteredFormat.textFormat.fontSize')
    if tf:
        cell_fmt['textFormat'] = tf

    if 'halign' in kwargs:
        cell_fmt['horizontalAlignment'] = kwargs['halign']
        field_paths.append('userEnteredFormat.horizontalAlignment')
    if 'valign' in kwargs:
        cell_fmt['verticalAlignment'] = kwargs['verticalAlignment']
        field_paths.append('userEnteredFormat.verticalAlignment')
    if 'wrap' in kwargs:
        cell_fmt['wrapStrategy'] = kwargs['wrap']
        field_paths.append('userEnteredFormat.wrapStrategy')

    return {
        "repeatCell": {
            "range": _range(sheet_id, r1, r2, c1, c2),
            "cell": {"userEnteredFormat": cell_fmt},
            "fields": ",".join(field_paths),
        }
    }


def borders_request(sheet_id, r1, r2, c1, c2, inner=True):
    b = {
        "range": _range(sheet_id, r1, r2, c1, c2),
        "top": THICK_BORDER, "bottom": THICK_BORDER,
        "left": THICK_BORDER, "right": THICK_BORDER,
    }
    if inner:
        b["innerHorizontal"] = THIN_BORDER
        b["innerVertical"] = THIN_BORDER
    return {"updateBorders": b}


def freeze_request(sheet_id, rows=1, cols=0):
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def col_width_request(sheet_id, col, px):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def row_height_request(sheet_id, row, px):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": row, "endIndex": row + 1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


# ── Inventory sheet ────────────────────────────────────────

def format_inventory(ws):
    sid = ws.id
    rows = ws.get_all_values()
    reqs = []

    # Find header row
    hdr_idx = next(
        (i for i, r in enumerate(rows) if any('Item ID' in str(c) for c in r)),
        None
    )
    if hdr_idx is None:
        print("  [Inventory] header row not found — skipping")
        return reqs

    hdr = rows[hdr_idx]
    n_cols = len(hdr)
    data_start = hdr_idx + 1
    data_end = len(rows)

    # Column indices by name
    def col(name):
        return next((i for i, h in enumerate(hdr) if name.lower() in h.lower()), None)

    status_col = col('Status')
    qty_col    = col('Current Qty') or col('Qty')

    # Title rows above header — make them look clean
    if hdr_idx > 0:
        reqs.append(fmt_request(sid, 0, hdr_idx, 0, max(n_cols, 2),
                                bg=C['title_bg'], color=C['title_text'],
                                bold=True, size=11, halign='CENTER'))
        reqs.append(row_height_request(sid, 0, 36))

    # Header row styling
    reqs.append(fmt_request(sid, hdr_idx, hdr_idx + 1, 0, n_cols,
                             bg=C['header_bg'], color=C['header_text'],
                             bold=True, size=10, halign='CENTER'))
    reqs.append(row_height_request(sid, hdr_idx, 30))

    # Data rows: alternating background + wrap
    for i in range(data_start, data_end):
        bg = C['alt_row'] if (i - data_start) % 2 == 1 else rgb(255, 255, 255)
        reqs.append(fmt_request(sid, i, i + 1, 0, n_cols, bg=bg, wrap='CLIP'))

    # Center-align ID, Qty cols, Status, Unit
    for c_idx in filter(lambda x: x is not None, [0, qty_col, col('Min'), col('Max'), col('Unit'), status_col]):
        reqs.append(fmt_request(sid, data_start, data_end, c_idx, c_idx + 1, halign='CENTER'))

    # Status colour coding + bold for alerts
    if status_col is not None:
        for i in range(data_start, data_end):
            row = rows[i] if i < len(rows) else []
            if len(row) <= status_col:
                continue
            v = row[status_col].strip().upper()
            color_map = {'OK': C['ok'], 'LOW STOCK': C['low_stock'], 'MISSING': C['missing']}
            if v in color_map:
                reqs.append(fmt_request(sid, i, i + 1, status_col, status_col + 1,
                                        bg=color_map[v],
                                        bold=(v != 'OK'),
                                        halign='CENTER'))

    # Borders
    reqs.append(borders_request(sid, hdr_idx, data_end, 0, n_cols))

    # Freeze through header
    reqs.append(freeze_request(sid, rows=hdr_idx + 1))

    # Column widths: ID, Name, Category, Qty, Min, Max, Unit, Status, Last Updated, Notes
    widths = [65, 170, 90, 85, 75, 75, 65, 100, 115, 220]
    for i, w in enumerate(widths[:n_cols]):
        reqs.append(col_width_request(sid, i, w))

    print(f"  [Inventory] {len(reqs)} requests, {data_end - data_start} data rows, header at row {hdr_idx + 1}")
    return reqs


# ── Transaction Log sheet ──────────────────────────────────

def format_transaction_log(ws):
    sid = ws.id
    rows = ws.get_all_values()
    reqs = []

    hdr_idx = next(
        (i for i, r in enumerate(rows) if any('Timestamp' in str(c) for c in r)),
        None
    )
    if hdr_idx is None:
        print("  [Transaction Log] header row not found — skipping")
        return reqs

    hdr = rows[hdr_idx]
    n_cols = len(hdr)
    data_start = hdr_idx + 1
    data_end = len(rows)

    def col(name):
        return next((i for i, h in enumerate(hdr) if name.lower() in h.lower()), None)

    action_col = col('Action')

    # Header row
    reqs.append(fmt_request(sid, hdr_idx, hdr_idx + 1, 0, n_cols,
                             bg=C['header_bg'], color=C['header_text'],
                             bold=True, size=10, halign='CENTER'))
    reqs.append(row_height_request(sid, hdr_idx, 30))

    # Alternating rows
    for i in range(data_start, data_end):
        bg = C['alt_row'] if (i - data_start) % 2 == 1 else rgb(255, 255, 255)
        reqs.append(fmt_request(sid, i, i + 1, 0, n_cols, bg=bg, wrap='CLIP'))

    # Center columns
    for c_idx in filter(lambda x: x is not None, [col('Item ID'), action_col, col('Quantity'), col('New Stock')]):
        reqs.append(fmt_request(sid, data_start, data_end, c_idx, c_idx + 1, halign='CENTER'))

    # Action colour
    if action_col is not None:
        for i in range(data_start, data_end):
            row = rows[i] if i < len(rows) else []
            if len(row) <= action_col:
                continue
            v = row[action_col].strip().upper()
            color_map = {'ADDED': C['added'], 'TAKEN': C['taken']}
            if v in color_map:
                reqs.append(fmt_request(sid, i, i + 1, action_col, action_col + 1,
                                        bg=color_map[v], bold=True, halign='CENTER'))

    # Borders + freeze
    reqs.append(borders_request(sid, hdr_idx, data_end, 0, n_cols))
    reqs.append(freeze_request(sid, rows=hdr_idx + 1))

    # Column widths: Timestamp, Item ID, Item Name, Action, Quantity, Raw Voice Command, New Stock
    widths = [140, 70, 160, 80, 80, 260, 100]
    for i, w in enumerate(widths[:n_cols]):
        reqs.append(col_width_request(sid, i, w))

    print(f"  [Transaction Log] {len(reqs)} requests, {data_end - data_start} data rows, header at row {hdr_idx + 1}")
    return reqs


# ── Other sheets (generic minimal formatting) ──────────────

def format_generic(ws):
    """Light formatting for any other sheets (e.g. Bot Log)."""
    sid = ws.id
    rows = ws.get_all_values()
    if not rows:
        return []
    reqs = []

    n_cols = max(len(r) for r in rows)

    # Bold first row as header
    reqs.append(fmt_request(sid, 0, 1, 0, n_cols,
                             bg=C['title_bg'], color=C['title_text'],
                             bold=True, halign='CENTER'))
    reqs.append(row_height_request(sid, 0, 28))

    # Alternating rows for the rest
    for i in range(1, len(rows)):
        bg = C['alt_row'] if i % 2 == 0 else rgb(255, 255, 255)
        reqs.append(fmt_request(sid, i, i + 1, 0, n_cols, bg=bg))

    reqs.append(borders_request(sid, 0, len(rows), 0, n_cols))
    reqs.append(freeze_request(sid, rows=1))
    print(f"  [{ws.title}] {len(reqs)} requests (generic format)")
    return reqs


# ── Main ───────────────────────────────────────────────────

def main():
    creds_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    client = gspread.authorize(creds)

    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    print(f"Opened: {spreadsheet.title!r}")

    worksheets = spreadsheet.worksheets()
    print(f"Sheets found: {[ws.title for ws in worksheets]}")

    all_requests = []
    for ws in worksheets:
        title = ws.title
        print(f"\nProcessing: {title!r}")
        if title == "Inventory":
            all_requests.extend(format_inventory(ws))
        elif title == "Transaction Log":
            all_requests.extend(format_transaction_log(ws))
        else:
            all_requests.extend(format_generic(ws))

    if all_requests:
        spreadsheet.batch_update({"requests": all_requests})
        print(f"\nDone — applied {len(all_requests)} formatting requests.")
    else:
        print("\nNo formatting requests generated.")


if __name__ == '__main__':
    main()
