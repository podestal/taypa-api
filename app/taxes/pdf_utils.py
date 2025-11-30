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


def number_to_words_es(amount: Decimal) -> str:
    """
    Convert a number to words in Spanish (Peruvian format)
    Example: 30.00 -> "Treinta con 00/100 Soles"
    """
    # Split integer and decimal parts
    integer_part = int(amount)
    decimal_part = int((amount - integer_part) * 100)
    
    # Spanish number names
    UNITS = ['', 'Uno', 'Dos', 'Tres', 'Cuatro', 'Cinco', 'Seis', 'Siete', 'Ocho', 'Nueve']
    TENS = ['', '', 'Veinte', 'Treinta', 'Cuarenta', 'Cincuenta', 'Sesenta', 'Setenta', 'Ochenta', 'Noventa']
    SPECIAL = {
        10: 'Diez', 11: 'Once', 12: 'Doce', 13: 'Trece', 14: 'Catorce',
        15: 'Quince', 16: 'Dieciséis', 17: 'Diecisiete', 18: 'Dieciocho', 19: 'Diecinueve'
    }
    HUNDREDS = ['', 'Cien', 'Doscientos', 'Trescientos', 'Cuatrocientos', 'Quinientos',
                'Seiscientos', 'Setecientos', 'Ochocientos', 'Novecientos']
    
    def convert_number(n):
        if n == 0:
            return 'Cero'
        if n < 10:
            return UNITS[n]
        if n < 20:
            return SPECIAL[n]
        if n < 100:
            tens = n // 10
            units = n % 10
            if units == 0:
                return TENS[tens]
            if tens == 2:
                return f'Veinti{UNITS[units].lower()}'
            return f'{TENS[tens]} y {UNITS[units]}'
        if n < 1000:
            hundreds = n // 100
            remainder = n % 100
            if remainder == 0:
                return HUNDREDS[hundreds]
            if hundreds == 1 and remainder > 0:
                return f'Ciento {convert_number(remainder)}'
            return f'{HUNDREDS[hundreds]} {convert_number(remainder)}'
        if n < 1000000:
            thousands = n // 1000
            remainder = n % 1000
            if remainder == 0:
                if thousands == 1:
                    return 'Mil'
                return f'{convert_number(thousands)} Mil'
            if thousands == 1:
                return f'Mil {convert_number(remainder)}'
            return f'{convert_number(thousands)} Mil {convert_number(remainder)}'
        return str(n)
    
    words = convert_number(integer_part)
    return f'Son {words} con {decimal_part:02d}/100 Soles'


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
    document_type: Optional[str] = None,  # 'ticket', 'boleta', or 'factura'
    document_code: Optional[str] = None,  # Serie-numero like "B001-00003"
    document_date: Optional[datetime] = None,  # Document emission date
    customer_razon_social: Optional[str] = None,  # For factura: company name
    customer_ruc: Optional[str] = None,  # For factura: company RUC
    customer_address: Optional[str] = None,  # For factura: company address
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
        document_type: Type of document ('ticket', 'boleta', 'factura')
        document_code: Document code (serie-numero)
        document_date: Document emission date
        customer_razon_social: For factura: customer company name
        customer_ruc: For factura: customer RUC
        customer_address: For factura: customer address
    
    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()
    
    # Calculate totals if not provided
    if total is None:
        total = Decimal(sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items))
    
    # For boleta/factura: Calculate IGV breakdown (IGV is included in prices)
    # For simple tickets: No IGV breakdown
    is_sunat_document = document_type in ['boleta', 'factura']
    
    if is_sunat_document:
        # IGV is included in prices, so calculate breakdown:
        # Op gravada = total / 1.18
        # IGV = total - op_gravada
        if subtotal is None:
            subtotal = total / Decimal('1.18')  # Taxable operation (Op gravada)
        if igv is None:
            igv = total - subtotal  # IGV amount
    else:
        # Simple ticket: no IGV breakdown
        if subtotal is None:
            subtotal = total
        if igv is None:
            igv = Decimal('0.00')
    
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
    
    # Document info for boleta/factura (after business info)
    if is_sunat_document and document_code:
        y_position -= 5
        # Document type title
        if document_type == 'boleta':
            y_position = draw_centered("Boleta de Venta Electronica", y_position, font_size=11, bold=True)
        elif document_type == 'factura':
            y_position = draw_centered("Factura Electronica", y_position, font_size=11, bold=True)
        
        # Document code (serie-numero)
        y_position = draw_centered(document_code, y_position, font_size=10, bold=True)
        
        # For factura: Show customer company info
        if document_type == 'factura':
            if customer_razon_social:
                y_position = draw_left(f"Nombre: {customer_razon_social}", y_position, font_size=9)
            if customer_ruc:
                y_position = draw_left(f"RUC: {customer_ruc}", y_position, font_size=9)
            if customer_address:
                y_position = draw_left(f"Direccion: {customer_address}", y_position, font_size=9)
            y_position -= 3
        
        # Emision (date and time)
        if document_date:
            emision_date = document_date
        else:
            emision_date = datetime.now()
        date_str = emision_date.strftime("%d/%m/%Y")
        time_str = emision_date.strftime("%H:%M:%S")
        y_position = draw_left(f"Emision: {date_str} {time_str}", y_position, font_size=9)
        
        # Moneda
        y_position = draw_left("Moneda: Sol (PEN)", y_position, font_size=9)
        y_position = draw_line(y_position)
    
    # Document/Order info for simple tickets (or customer name for boleta)
    if not is_sunat_document:
        y_position -= 5
        if order_number:
            # Simple order number, show as "Orden: X"
            y_position = draw_left(f"Orden: {order_number}", y_position, font_size=10, bold=True)
        if customer_name:
            y_position = draw_left(f"Cliente: {customer_name}", y_position, font_size=10)
        
        # Date and time (for simple tickets only)
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y")
        time_str = now.strftime("%H:%M:%S")
        y_position = draw_left(f"Fecha: {date_str} {time_str}", y_position, font_size=9)
    elif customer_name and document_type == 'boleta':
        # For boleta: show customer name if available
        y_position -= 5
        y_position = draw_left(f"Cliente: {customer_name}", y_position, font_size=10)
    
    if not is_sunat_document or (is_sunat_document and not document_code):
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
    
    if is_sunat_document:
        # For boleta/factura: Show IGV breakdown
        y_position = draw_left("Op gravada", y_position, font_size=10, bold=True)
        y_position = draw_right(f"S/ {subtotal:.2f}", y_position, font_size=10, bold=True)
        y_position = draw_left("IGV (18%)", y_position, font_size=10, bold=True)
        y_position = draw_right(f"S/ {igv:.2f}", y_position, font_size=10, bold=True)
        y_position = draw_line(y_position)
        y_position -= 3
        y_position = draw_left("Importe total", y_position, font_size=12, bold=True)
        y_position = draw_right(f"S/ {total:.2f}", y_position, font_size=12, bold=True)
        
        # Add amount in words
        y_position -= 5
        amount_words = number_to_words_es(total)
        # Wrap text if too long
        if len(amount_words) > 40:
            words_parts = amount_words.split(' ')
            line1 = ' '.join(words_parts[:len(words_parts)//2])
            line2 = ' '.join(words_parts[len(words_parts)//2:])
            y_position = draw_left(line1, y_position, font_size=9)
            y_position = draw_left(line2, y_position, font_size=9)
        else:
            y_position = draw_left(amount_words, y_position, font_size=9)
    else:
        # For simple tickets: Just show total
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
