"""
Utility functions for generating PDF tickets (80mm thermal printer format)
No Sunat connection - generates tickets locally
"""
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors


# 80mm thermal printer dimensions (in points)
# 80mm = 226.77 points (1mm = 2.83465 points)
TICKET_WIDTH = 80 * mm  # 226.77 points
TICKET_HEIGHT = A4[1]  # Use full height, will adjust based on content


def generate_ticket_pdf(
    order_items: List[Dict],
    business_name: str = "Axios",
    business_address: str = "217 primera",
    business_ruc: str = "20482674828",
    order_number: Optional[str] = None,
    customer_name: Optional[str] = None,
    subtotal: Optional[Decimal] = None,
    igv: Optional[Decimal] = None,
    total: Optional[Decimal] = None,
) -> BytesIO:
    """
    Generate a PDF ticket for 80mm thermal printer
    
    Args:
        order_items: List of items with 'name', 'quantity', 'cost'
        business_name: Business name
        business_address: Business address
        business_ruc: Business RUC
        order_number: Order number (optional)
        customer_name: Customer name (optional)
        subtotal: Subtotal amount (optional, will calculate if not provided)
        igv: IGV tax amount (optional, will calculate if not provided)
        total: Total amount (optional, will calculate if not provided)
    
    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()
    
    # Calculate totals if not provided
    if total is None:
        total = Decimal(sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items))
    
    if subtotal is None:
        # Assuming prices include IGV, calculate subtotal
        subtotal = total / Decimal('1.18')  # IGV is 18%
    
    if igv is None:
        igv = total - subtotal
    
    # Create PDF canvas
    c = canvas.Canvas(buffer, pagesize=(TICKET_WIDTH, TICKET_HEIGHT))
    width = TICKET_WIDTH
    y_position = TICKET_HEIGHT - 20  # Start from top with margin
    
    # Helper function to draw centered text
    def draw_centered(text, y, font_name='Helvetica', font_size=12, bold=False):
        c.setFont(font_name + '-Bold' if bold else font_name, font_size)
        text_width = c.stringWidth(text, font_name + '-Bold' if bold else font_name, font_size)
        x = (width - text_width) / 2
        c.drawString(x, y, text)
        return y - (font_size + 5)
    
    # Helper function to draw left-aligned text
    def draw_left(text, y, font_name='Helvetica', font_size=10, bold=False):
        c.setFont(font_name + '-Bold' if bold else font_name, font_size)
        c.drawString(10, y, text)
        return y - (font_size + 3)
    
    # Helper function to draw right-aligned text
    def draw_right(text, y, font_name='Helvetica', font_size=10, bold=False):
        c.setFont(font_name + '-Bold' if bold else font_name, font_size)
        text_width = c.stringWidth(text, font_name + '-Bold' if bold else font_name, font_size)
        x = width - text_width - 10
        c.drawString(x, y, text)
        return y - (font_size + 3)
    
    # Helper function to draw line
    def draw_line(y):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(10, y, width - 10, y)
        return y - 5
    
    # Header
    y_position = draw_centered(business_name, y_position, font_size=16, bold=True)
    y_position = draw_centered(business_address, y_position, font_size=10)
    y_position = draw_centered(f"RUC: {business_ruc}", y_position, font_size=9)
    y_position = draw_line(y_position)
    
    # Order info
    y_position -= 5
    if order_number:
        y_position = draw_left(f"Orden: {order_number}", y_position, font_size=10, bold=True)
    if customer_name:
        y_position = draw_left(f"Cliente: {customer_name}", y_position, font_size=10)
    
    # Date and time
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M:%S")
    y_position = draw_left(f"Fecha: {date_str} {time_str}", y_position, font_size=9)
    y_position = draw_line(y_position)
    
    # Items header
    y_position -= 5
    y_position = draw_left("DESCRIPCIÓN", y_position, font_size=9, bold=True)
    y_position = draw_right("TOTAL", y_position, font_size=9, bold=True)
    y_position = draw_line(y_position)
    
    # Order items
    y_position -= 3
    for item in order_items:
        name = str(item.get('name', ''))
        quantity = float(item.get('quantity', 0))
        cost = float(item.get('cost', 0))
        item_total = quantity * cost
        
        # Item name (may need to wrap if too long)
        item_text = f"{name}"
        if len(item_text) > 30:
            item_text = item_text[:27] + "..."
        
        y_position = draw_left(item_text, y_position, font_size=9)
        
        # Quantity and price on same line
        qty_price_text = f"{quantity:.2f} x {cost:.2f}"
        y_position = draw_left(qty_price_text, y_position, font_size=8)
        
        # Item total
        y_position = draw_right(f"S/ {item_total:.2f}", y_position, font_size=9)
        y_position -= 3
    
    # Totals section
    y_position = draw_line(y_position)
    y_position -= 5
    y_position = draw_left("SUBTOTAL", y_position, font_size=10, bold=True)
    y_position = draw_right(f"S/ {subtotal:.2f}", y_position, font_size=10, bold=True)
    y_position = draw_left("IGV (18%)", y_position, font_size=10, bold=True)
    y_position = draw_right(f"S/ {igv:.2f}", y_position, font_size=10, bold=True)
    y_position = draw_line(y_position)
    y_position -= 3
    y_position = draw_left("TOTAL", y_position, font_size=12, bold=True)
    y_position = draw_right(f"S/ {total:.2f}", y_position, font_size=12, bold=True)
    
    # Footer
    y_position = draw_line(y_position)
    y_position -= 10
    y_position = draw_centered("¡Gracias por su compra!", y_position, font_size=10)
    y_position -= 5
    y_position = draw_centered("Vuelva pronto", y_position, font_size=9)
    
    # Finalize PDF
    c.save()
    buffer.seek(0)
    return buffer

