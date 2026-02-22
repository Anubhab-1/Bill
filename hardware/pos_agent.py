#!/usr/bin/env python3
"""
Mall Billing System - Local POS Hardware Agent
==============================================
This script runs locally on the cashier's computer. It bridges the 
cloud-based Mall Billing web app to the local USB/Network thermal 
printer and cash drawer via a local WebSocket server.

Install dependencies:
    pip install -r requirements.txt

Run:
    python pos_agent.py
"""

import asyncio
import json
import logging
from websockets.server import serve
from escpos.printer import Usb, Network, Dummy

# --- Configuration ---
# Set your printer connection type here ('usb', 'network', 'dummy' for testing)
PRINTER_TYPE = 'dummy' 

# If USB: Find these using `lsusb` (Linux) or Device Manager (Windows)
USB_VENDOR_ID = 0x04b8
USB_PRODUCT_ID = 0x0202

# If Network: 
PRINTER_IP = '192.168.1.100'

# WebSocket Port (must match the web app script)
WS_PORT = 8765

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_printer():
    """Initializes and returns the escpos printer object based on config."""
    try:
        if PRINTER_TYPE == 'usb':
            # Note: On Windows, libusb is required for standard python-escpos USB support.
            # Alternatively, you can share the printer and use win32print, but Dummy 
            # is used here as a safe cross-platform default for demonstration.
            return Usb(USB_VENDOR_ID, USB_PRODUCT_ID, timeout=0, in_ep=0x81, out_ep=0x03)
        elif PRINTER_TYPE == 'network':
            return Network(PRINTER_IP)
        else:
            logging.info("Using Dummy printer (output goes to console/memory only).")
            return Dummy()
    except Exception as e:
        logging.error(f"Failed to connect to printer: {e}")
        return None

def print_receipt(receipt_data):
    """Formats and prints the receipt using ESC/POS."""
    printer = get_printer()
    if not printer:
        return False, "Printer connection failed"

    try:
        # Header
        printer.set(align='center', bold=True, double_height=True, double_width=True)
        printer.text("MALL BILLING\n")
        printer.set(align='center', bold=False, double_height=False, double_width=False)
        printer.text("The Premiere Shopping Destination\n")
        printer.text("123 Commerce Way, Retail District\n")
        printer.text(f"Tax Invoice: {receipt_data.get('invoice_number', 'N/A')}\n")
        printer.text("-" * 48 + "\n")

        # Items
        printer.set(align='left')
        for item in receipt_data.get('items', []):
            # Format: 1x T-Shirt @ $20.00 = $20.00
            line1 = f"{item['qty']}x {item['name'][:25]}"
            printer.text(f"{line1}\n")
            line2 = f"   @ {float(item['price']):.2f}"
            total_str = f"{float(item['subtotal']):.2f}"
            # Right align the total
            spaces = 48 - len(line2) - len(total_str)
            printer.text(f"{line2}{' ' * max(1, spaces)}{total_str}\n")

        printer.text("-" * 48 + "\n")

        # Totals
        printer.set(align='right', bold=True)
        printer.text(f"Subtotal: {float(receipt_data.get('subtotal', 0)):.2f}\n")
        printer.text(f"GST: {float(receipt_data.get('gst_total', 0)):.2f}\n")
        
        printer.set(double_height=True, double_width=True)
        printer.text(f"TOTAL: {float(receipt_data.get('grand_total', 0)):.2f}\n")
        printer.set(double_height=False, double_width=False)

        printer.text("\n")
        printer.set(align='center')
        printer.text("Thank you for your purchase!\n")
        printer.text("Please retain this receipt for returns.\n")
        printer.text("\n\n")

        # Print Barcode (if invoice number is clean alphanumeric)
        inv = receipt_data.get('invoice_number', '')
        if inv.replace('-', '').isalnum():
            try:
                printer.barcode(inv.replace('-', ''), 'CODE39', 64, 2, '', '')
            except Exception:
                pass # skip barcode if unsupported by specific model

        # Cut paper
        printer.cut()
        
        if isinstance(printer, Dummy):
            logging.info("--- DUMMY PRINTER OUTPUT ---")
            print(printer.output.decode('utf-8', errors='ignore'))
            logging.info("----------------------------")

        printer.close()
        return True, "Printed successfully"

    except Exception as e:
        logging.error(f"Printing error: {e}")
        return False, str(e)


def open_cash_drawer():
    """Sends the standard ESC/POS pulse to kick the RJ11 cash drawer."""
    printer = get_printer()
    if not printer:
        return False, "Printer connection failed"

    try:
        # Standard kick drawer pulse 
        printer.cashdraw(2)
        
        if isinstance(printer, Dummy):
            logging.info("🔔 [DUMMY] Cash drawer kicked open!")

        printer.close()
        return True, "Drawer opened"
    except Exception as e:
        logging.error(f"Drawer error: {e}")
        return False, str(e)


async def handle_request(websocket):
    """WebSocket connection handler."""
    client_ip = websocket.remote_address[0]
    logging.info(f"Client connected from {client_ip}")

    # For security, only allow local connections
    if client_ip not in ('127.0.0.1', '::1', 'localhost'):
        logging.warning("Rejected non-local connection.")
        await websocket.close()
        return

    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
                action = payload.get("action")
                
                if action == "print_receipt":
                    logging.info("Received print job.")
                    success, msg = print_receipt(payload.get("data", {}))
                    await websocket.send(json.dumps({"status": "success" if success else "error", "message": msg}))
                
                elif action == "open_drawer":
                    logging.info("Received open drawer request.")
                    success, msg = open_cash_drawer()
                    await websocket.send(json.dumps({"status": "success" if success else "error", "message": msg}))
                
                elif action == "ping":
                    await websocket.send(json.dumps({"status": "ok", "message": "pos_agent online"}))
                
                else:
                    await websocket.send(json.dumps({"status": "error", "message": "Unknown action"}))
                    
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"status": "error", "message": "Invalid JSON payload"}))
                
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        logging.info("Client disconnected.")

async def main():
    async with serve(handle_request, "localhost", WS_PORT):
        logging.info(f"🚀 POS Hardware Agent running on ws://localhost:{WS_PORT}")
        logging.info(f"Target Printer Type: {PRINTER_TYPE.upper()}")
        logging.info("Waiting for web app connection...")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("POS Agent shutting down.")
