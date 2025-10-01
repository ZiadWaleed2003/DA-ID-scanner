import streamlit as st
from datetime import datetime
import gspread
import csv
from google.oauth2.service_account import Credentials
import os
import traceback

# Single spreadsheet ID
SHEET_ID = "1o1cjx-GzJcw7_bXfkLtkDXDzmi6bLj6GdLpab-sHoY8"

# Map station -> tab name inside the spreadsheet
STATION_TABS = {
    "DUD2": "DUD2",
    "DUD3": "DUD3",
    "DAD2": "DAD2",
    "DAD8": "DAD8",
    "DUD5": "DUD5"
}


def initialize_google_sheets():
    """Initialize Google Sheets connection and store in session state"""
    if 'sheets_initialized' not in st.session_state:
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            # Try to load from Streamlit secrets (TOML format)
            try:
                service_account_info = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
            except Exception:
                # Fallback to JSON file for local development
                creds = Credentials.from_service_account_file("service_account1.json", scopes=scopes)
            
            client = gspread.authorize(creds)

            # Open the spreadsheet once
            spreadsheet = client.open_by_key(SHEET_ID)

            # Map station -> worksheet object
            sheets = {}
            for station, tab_name in STATION_TABS.items():
                try:
                    # Try to open existing worksheet
                    sheets[station] = spreadsheet.worksheet(tab_name)
                except gspread.WorksheetNotFound:
                    # If not found, create the worksheet automatically
                    st.write(f"Tab '{tab_name}' not found. Creating new tab...")
                    sheets[station] = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=10)
                except Exception as e:
                    st.write(f"Failed to open tab for {station}: {e}")
                    sheets[station] = None

            st.session_state.sheets = sheets
            st.session_state.status_text = "Connected to Google Sheets ✅"
            st.session_state.sheets_initialized = True

        except Exception as e:
            st.session_state.sheets = {}
            st.session_state.status_text = f"Google Sheets connection failed ❌: {e}"
            st.session_state.sheets_initialized = True
            print(traceback.format_exc())

def initialize_session_state():
    """Initialize all session state variables"""
    if 'local_data' not in st.session_state:
        st.session_state.local_data = []
    if 'stations' not in st.session_state:
        st.session_state.stations = list(STATION_TABS.keys())
    if 'status_text' not in st.session_state:
        st.session_state.status_text = "Initializing..."
    if 'count_message' not in st.session_state:
        st.session_state.count_message = ""
    if 'count_color' not in st.session_state:
        st.session_state.count_color = "lightgreen"

def scan_id(driver_id, station):
    """Process a driver ID scan"""
    if not driver_id.strip():
        st.error("Please enter a Driver ID")
        return

    scan_time = datetime.now().strftime('%H:%M:%S')
    scan_date = datetime.now().strftime('%Y-%m-%d')

    # Save locally (memory)
    st.session_state.local_data.append((driver_id, scan_time, scan_date, station))
    st.session_state.status_text = f"Scanned locally: {driver_id} @ {station}"

    # Save to CSV backup
    save_to_csv(driver_id, scan_time, scan_date, station)

    # Count how many times this driver has been scanned today at this station
    today_scans = [d for d in st.session_state.local_data if d[0] == driver_id and d[2] == scan_date and d[3] == station]
    count = len(today_scans)

    # Update the count message and color
    if count > 5:
        st.session_state.count_message = f"Driver {driver_id} scanned {count} times at {station} - Take break after this delivery"
        st.session_state.count_color = "yellow"
    else:
        st.session_state.count_message = f"Driver {driver_id} scanned {count} times today at {station}"
        st.session_state.count_color = "lightgreen"

    # Try sync to Google Sheets
    sync_single_scan(driver_id, scan_time, scan_date, station)

def save_to_csv(driver_id, scan_time, scan_date, station):
    """Backup scan data to a local CSV file for the selected station."""
    filename = f"{station}_scans.csv"
    file_exists = os.path.isfile(filename)

    with open(filename, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Driver ID", "Scan Time", "Scan Date", "Station", "Saved At"])
        writer.writerow([driver_id, scan_time, scan_date, station, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

def sync_single_scan(driver_id, scan_time, scan_date, station):
    """Push a single scan to the Google Sheet for the selected station."""
    sheet = st.session_state.sheets.get(station)
    if not sheet:
        st.session_state.status_text = f"No Google Sheet tab available for {station}"
        return

    try:
        existing_data = sheet.get_all_values()

        # Add header if sheet is empty
        if not existing_data:
            sheet.append_row(["Driver ID", "Scan Time", "Scan Date", "Station", "Uploaded At"])

        # Find the first empty row (after header)
        values = sheet.col_values(1)  # check first column (Driver ID)
        next_row = len(values) + 1 if values else 2  # row after last filled one, or row 2 if empty

        # Write data into that row (new gspread syntax, avoids warning)
        sheet.update(
            range_name=f"A{next_row}:E{next_row}",
            values=[[driver_id, scan_time, scan_date, station, datetime.now().strftime('%Y-%m-%d %H:%M:%S')]]
        )

        st.session_state.status_text = f"Uploaded to {station} Google Sheet tab: {driver_id}"

    except Exception as e:
        st.session_state.status_text = f"Google Sheets sync failed: {e}"
        print(traceback.format_exc())


def main():
    """Main Streamlit app"""
    st.set_page_config(page_title="DA ID Scanner", page_icon="🚛", layout="centered")
    
    # Initialize session state
    initialize_session_state()
    
    # Initialize Google Sheets connection
    initialize_google_sheets()
    
    # App title
    st.title("🚛 DA ID Scanner")
    
    # Station selection
    st.subheader("Station Selection")
    selected_station = st.selectbox(
        "Choose Station:",
        st.session_state.stations,
        index=0
    )
    
    # Driver ID input form
    st.subheader("Driver ID Scan")
    
    with st.form("scan_form", clear_on_submit=True):
        driver_id = st.text_input("Driver ID:", placeholder="Enter driver ID and press Enter or click Scan")
        scan_button = st.form_submit_button("🔍 Scan", use_container_width=True)
        
        if scan_button and driver_id:
            scan_id(driver_id, selected_station)
    
    # Status display
    st.subheader("Status")
    
    # Connection status
    if st.session_state.status_text:
        if "✅" in st.session_state.status_text:
            st.success(st.session_state.status_text)
        elif "❌" in st.session_state.status_text:
            st.error(st.session_state.status_text)
        else:
            st.info(st.session_state.status_text)
    
    # Count display with color coding
    if st.session_state.count_message:
        if st.session_state.count_color == "yellow":
            st.warning(st.session_state.count_message)
        else:
            st.success(st.session_state.count_message)
    
    # Display recent scans
    if st.session_state.local_data:
        st.subheader("Recent Scans")
        
        # Show last 10 scans
        recent_scans = st.session_state.local_data[-10:]
        scan_data = []
        for scan in reversed(recent_scans):  # Show most recent first
            scan_data.append({
                "Driver ID": scan[0],
                "Time": scan[1],
                "Date": scan[2],
                "Station": scan[3]
            })
        
        st.dataframe(scan_data, use_container_width=True)

if __name__ == "__main__":
    main()