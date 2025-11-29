"""
Utilities for generating Sunat documents (invoices and tickets)
Handles correlative numbers, number to words conversion, and document body generation
"""
import requests
from datetime import datetime
from typing import Dict, Optional, List, Literal
from django.conf import settings


def number_to_words(amount: float) -> str:
    """
    Convert a number to words in Spanish (for legal document requirements)
    
    Args:
        amount: The amount to convert (e.g., 123.45)
        
    Returns:
        String like "CIENTO VEINTITRÉS CON 45/100 SOLES"
    """
    units = [
        "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
        "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE"
    ]
    
    tens = ["", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    
    hundreds = [
        "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
        "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"
    ]
    
    def convert_integer(num: int) -> str:
        """Recursively convert integer to words"""
        if num == 0:
            return "CERO"
        if num == 100:
            return "CIEN"
        if num < 20:
            return units[num]
        if num < 100:
            ten_part = tens[num // 10]
            unit_part = units[num % 10]
            remainder = num % 10
            
            if remainder != 0:
                # Handle 21-29 specially (VEINTIUNO, VEINTIDÓS, etc.)
                if 21 <= num <= 29:
                    special = {
                        21: "VEINTIUNO", 22: "VEINTIDÓS", 23: "VEINTITRÉS",
                        24: "VEINTICUATRO", 25: "VEINTICINCO", 26: "VEINTISÉIS",
                        27: "VEINTISIETE", 28: "VEINTIOCHO", 29: "VEINTINUEVE"
                    }
                    return special[num]
                return ten_part + " Y " + unit_part
            return ten_part
        if num < 1000:
            hundred_part = hundreds[num // 100]
            remainder = num % 100
            if remainder != 0:
                return hundred_part + " " + convert_integer(remainder)
            return hundred_part
        if num < 1000000:
            thousands = num // 1000
            remainder = num % 1000
            thousands_word = "MIL" if thousands == 1 else convert_integer(thousands) + " MIL"
            if remainder != 0:
                return thousands_word + " " + convert_integer(remainder)
            return thousands_word
        return "CANTIDAD MUY ALTA"
    
    # Format amount to 2 decimal places
    formatted_amount = f"{amount:.2f}"
    integer_part, decimal_part = formatted_amount.split(".")
    
    integer_num = int(integer_part)
    words = f"{convert_integer(integer_num)} CON {decimal_part}/100 SOLES"
    
    return words


def get_correlative(document_type: Literal['I', 'T']) -> Optional[str]:
    """
    Get the next correlative number from Sunat API
    
    Args:
        document_type: 'I' for Invoice, 'T' for Ticket
        
    Returns:
        Suggested number string (e.g., "00000001") or None if error
    """
    doc_type = '01' if document_type == 'I' else '03'
    doc_serie = 'F001' if document_type == 'I' else 'B001'
    
    persona_id = settings.SUNAT_PERSONA_ID
    persona_token = settings.SUNAT_PERSONA_TOKEN
    
    if not persona_id or not persona_token:
        raise ValueError("Sunat API credentials not configured")
    
    data = {
        'personaId': persona_id,
        'personaToken': persona_token,
        'type': doc_type,
        'serie': doc_serie,
    }
    
    try:
        response = requests.post(
            'https://back.apisunat.com/personas/lastDocument/',
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result.get('suggestedNumber')
    except Exception as e:
        print(f"Error getting correlative: {str(e)}")
        return None


def get_item_list(order_items: List[Dict]) -> List[Dict]:
    """
    Convert order items to Sunat invoice line format
    
    Args:
        order_items: List of items with keys: id, name, quantity, cost
        Note: cost should be the price WITH IGV already included
        
    Returns:
        List of invoice line dictionaries in Sunat format
    """
    # First, calculate total to avoid rounding errors
    total_with_igv = sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items)
    
    # Calculate base and tax from total (avoid rounding until the end)
    base_total = total_with_igv / 1.18
    tax_total = base_total * 0.18
    
    item_list = []
    accumulated_base = 0
    accumulated_tax = 0
    
    for idx, item in enumerate(order_items):
        item_id = str(item.get('id', ''))
        quantity = float(item.get('quantity', 0))
        cost_with_igv = float(item.get('cost', 0))  # Price already includes IGV
        name = item.get('name', '')
        
        # Calculate item line total
        item_total_with_igv = quantity * cost_with_igv
        
        # Calculate proportional base and tax
        if idx == len(order_items) - 1:
            # Last item: use remaining amount to avoid rounding errors
            line_extension = round(base_total - accumulated_base, 2)
            tax_amount = round(tax_total - accumulated_tax, 2)
        else:
            # Calculate proportionally
            proportion = item_total_with_igv / total_with_igv
            line_extension = round(base_total * proportion, 2)
            tax_amount = round(tax_total * proportion, 2)
        
        accumulated_base += line_extension
        accumulated_tax += tax_amount
        
        # Base cost per unit (for display in XML)
        base_cost = round(line_extension / quantity, 2) if quantity > 0 else 0
        price_with_tax = cost_with_igv  # Original price already includes IGV
        
        invoice_line = {
            "cbc:ID": {
                "_text": item_id
            },
            "cbc:InvoicedQuantity": {
                "_attributes": {
                    "unitCode": "NIU"
                },
                "_text": quantity
            },
            "cbc:LineExtensionAmount": {
                "_attributes": {
                    "currencyID": "PEN"
                },
                "_text": line_extension
            },
            "cac:PricingReference": {
                "cac:AlternativeConditionPrice": {
                    "cbc:PriceAmount": {
                        "_attributes": {
                            "currencyID": "PEN"
                        },
                        "_text": price_with_tax
                    },
                    "cbc:PriceTypeCode": {
                        "_text": "01"
                    }
                }
            },
            "cac:TaxTotal": {
                "cbc:TaxAmount": {
                    "_attributes": {
                        "currencyID": "PEN"
                    },
                    "_text": tax_amount
                },
                "cac:TaxSubtotal": [
                    {
                        "cbc:TaxableAmount": {
                            "_attributes": {
                                "currencyID": "PEN"
                            },
                            "_text": line_extension
                        },
                        "cbc:TaxAmount": {
                            "_attributes": {
                                "currencyID": "PEN"
                            },
                            "_text": tax_amount
                        },
                        "cac:TaxCategory": {
                            "cbc:Percent": {
                                "_text": 18
                            },
                            "cbc:TaxExemptionReasonCode": {
                                "_text": "10"
                            },
                            "cac:TaxScheme": {
                                "cbc:ID": {
                                    "_text": "1000"
                                },
                                "cbc:Name": {
                                    "_text": "IGV"
                                },
                                "cbc:TaxTypeCode": {
                                    "_text": "VAT"
                                }
                            }
                        }
                    }
                ]
            },
            "cac:Item": {
                "cbc:Description": {
                    "_text": name
                }
            },
            "cac:Price": {
                "cbc:PriceAmount": {
                    "_attributes": {
                        "currencyID": "PEN"
                    },
                    "_text": base_cost  # Base price without IGV
                }
            }
        }
        
        item_list.append(invoice_line)
    
    return item_list


def generate_invoice_data(
    correlative: str,
    order_items: List[Dict],
    ruc: str,
    razon_social: str,
    address: str,
    supplier_ruc: str = "20482674828",
    supplier_name: str = "Axios",
    supplier_address: str = "217 primera"
) -> Dict:
    """
    Generate invoice document data for Sunat API
    
    Args:
        correlative: Document number (e.g., "00000001")
        order_items: List of items with keys: id, name, quantity, cost
        ruc: Customer RUC
        razon_social: Customer legal company name (razón social)
        address: Customer address
        supplier_ruc: Supplier RUC (default: "20482674828")
        supplier_name: Supplier name (default: "Axios")
        supplier_address: Supplier address (default: "217 primera")
        
    Returns:
        Dictionary with invoice data ready for Sunat API
    """
    # Calculate totals - avoid rounding errors
    # Note: cost already includes IGV
    total_with_igv = sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items)
    # Calculate precisely first, round only at the end
    sub_total = total_with_igv / 1.18
    taxes = sub_total * 0.18
    total = sub_total + taxes  # Should equal total_with_igv exactly
    
    # Round only final values
    sub_total = round(sub_total, 2)
    taxes = round(taxes, 2)
    # Use original total_with_igv to avoid rounding errors - this is exactly what user sent
    total = round(total_with_igv, 2)
    
    # Get item list (uses same totals calculation internally)
    item_list = get_item_list(order_items)
    
    # Current date and time
    now = datetime.now()
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")
    
    # Generate words for total amount
    total_words = number_to_words(total)
    
    invoice = {
        "personaId": settings.SUNAT_PERSONA_ID,
        "personaToken": settings.SUNAT_PERSONA_TOKEN,
        "fileName": f"{supplier_ruc}-01-F001-{correlative}",
        "documentBody": {
            "cbc:UBLVersionID": {"_text": "2.1"},
            "cbc:CustomizationID": {"_text": "2.0"},
            "cbc:ID": {"_text": f"F001-{correlative}"},
            "cbc:IssueDate": {"_text": issue_date},
            "cbc:IssueTime": {"_text": issue_time},
            "cbc:InvoiceTypeCode": {
                "_attributes": {"listID": "0101"},
                "_text": "01",
            },
            "cbc:Note": [
                {
                    "_text": total_words,
                    "_attributes": {"languageLocaleID": "1000"},
                },
            ],
            "cbc:DocumentCurrencyCode": {"_text": "PEN"},
            "cac:AccountingSupplierParty": {
                "cac:Party": {
                    "cac:PartyIdentification": {
                        "cbc:ID": {
                            "_attributes": {"schemeID": "6"},
                            "_text": supplier_ruc,
                        },
                    },
                    "cac:PartyName": {"cbc:Name": {"_text": supplier_name}},
                    "cac:PartyLegalEntity": {
                        "cbc:RegistrationName": {"_text": supplier_name},
                        "cac:RegistrationAddress": {
                            "cbc:AddressTypeCode": {"_text": "0000"},
                            "cac:AddressLine": {"cbc:Line": {"_text": supplier_address}},
                        },
                    },
                },
            },
            "cac:AccountingCustomerParty": {
                "cac:Party": {
                    "cac:PartyIdentification": {
                        "cbc:ID": {
                            "_attributes": {"schemeID": "6"},
                            "_text": ruc,
                        },
                    },
                    "cac:PartyLegalEntity": {
                        "cbc:RegistrationName": {"_text": razon_social},
                        "cac:RegistrationAddress": {
                            "cac:AddressLine": {"cbc:Line": {"_text": address}},
                        },
                    },
                },
            },
            "cac:TaxTotal": {
                "cbc:TaxAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": taxes,
                },
                "cac:TaxSubtotal": [
                    {
                        "cbc:TaxableAmount": {
                            "_attributes": {"currencyID": "PEN"},
                            "_text": sub_total,
                        },
                        "cbc:TaxAmount": {
                            "_attributes": {"currencyID": "PEN"},
                            "_text": taxes,
                        },
                        "cac:TaxCategory": {
                            "cac:TaxScheme": {
                                "cbc:ID": {"_text": "1000"},
                                "cbc:Name": {"_text": "IGV"},
                                "cbc:TaxTypeCode": {"_text": "VAT"},
                            },
                        },
                    },
                ],
            },
            "cac:LegalMonetaryTotal": {
                "cbc:LineExtensionAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": sub_total,
                },
                "cbc:TaxInclusiveAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": total,
                },
                "cbc:PayableAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": total,
                },
            },
            "cac:PaymentTerms": [
                {
                    "cbc:ID": {"_text": "FormaPago"},
                    "cbc:PaymentMeansID": {"_text": "Contado"},
                },
            ],
            "cac:InvoiceLine": item_list
        },
    }
    
    return invoice


def generate_ticket_data(
    correlative: str,
    order_items: List[Dict],
    supplier_ruc: str = "20482674828",
    supplier_name: str = "Axios",
    supplier_address: str = "217 primera"
) -> Dict:
    """
    Generate ticket (boleta) document data for Sunat API
    
    Args:
        correlative: Document number (e.g., "00000001")
        order_items: List of items with keys: id, name, quantity, cost
        supplier_ruc: Supplier RUC (default: "20482674828")
        supplier_name: Supplier name (default: "Axios")
        supplier_address: Supplier address (default: "217 primera")
        
    Returns:
        Dictionary with ticket data ready for Sunat API
    """
    # Calculate totals - avoid rounding errors
    # Note: cost already includes IGV
    total_with_igv = sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items)
    # Calculate precisely first, round only at the end
    sub_total = total_with_igv / 1.18
    taxes = sub_total * 0.18
    total = sub_total + taxes  # Should equal total_with_igv exactly
    
    # Round only final values
    sub_total = round(sub_total, 2)
    taxes = round(taxes, 2)
    # Use original total_with_igv to avoid rounding errors - this is exactly what user sent
    total = round(total_with_igv, 2)
    
    # Get item list (uses same totals calculation internally)
    item_list = get_item_list(order_items)
    
    # Current date and time
    now = datetime.now()
    issue_date = now.strftime("%Y-%m-%d")
    issue_time = now.strftime("%H:%M:%S")
    
    # Generate words for total amount
    total_words = number_to_words(total)
    
    ticket = {
        "personaId": settings.SUNAT_PERSONA_ID,
        "personaToken": settings.SUNAT_PERSONA_TOKEN,
        "fileName": f"{supplier_ruc}-03-B001-{correlative}",
        "documentBody": {
            "cbc:UBLVersionID": {"_text": "2.1"},
            "cbc:CustomizationID": {"_text": "2.0"},
            "cbc:ID": {"_text": f"B001-{correlative}"},
            "cbc:IssueDate": {"_text": issue_date},
            "cbc:IssueTime": {"_text": issue_time},
            "cbc:InvoiceTypeCode": {
                "_attributes": {"listID": "0101"},
                "_text": "03",
            },
            "cbc:Note": [
                {
                    "_text": total_words,
                    "_attributes": {"languageLocaleID": "1000"},
                },
            ],
            "cbc:DocumentCurrencyCode": {"_text": "PEN"},
            "cac:AccountingSupplierParty": {
                "cac:Party": {
                    "cac:PartyIdentification": {
                        "cbc:ID": {"_attributes": {"schemeID": "6"}, "_text": supplier_ruc},
                    },
                    "cac:PartyName": {"cbc:Name": {"_text": supplier_name}},
                    "cac:PartyLegalEntity": {
                        "cbc:RegistrationName": {"_text": supplier_name},
                        "cac:RegistrationAddress": {
                            "cbc:AddressTypeCode": {"_text": "0000"},
                            "cac:AddressLine": {"cbc:Line": {"_text": supplier_address}},
                        },
                    },
                },
            },
            "cac:AccountingCustomerParty": {
                "cac:Party": {
                    "cac:PartyIdentification": {
                        "cbc:ID": {"_attributes": {"schemeID": "1"}, "_text": "00000000"},
                    },
                    "cac:PartyLegalEntity": {"cbc:RegistrationName": {"_text": "---"}},
                },
            },
            "cac:TaxTotal": {
                "cbc:TaxAmount": {"_attributes": {"currencyID": "PEN"}, "_text": taxes},
                "cac:TaxSubtotal": [
                    {
                        "cbc:TaxableAmount": {"_attributes": {"currencyID": "PEN"}, "_text": sub_total},
                        "cbc:TaxAmount": {"_attributes": {"currencyID": "PEN"}, "_text": taxes},
                        "cac:TaxCategory": {
                            "cac:TaxScheme": {
                                "cbc:ID": {"_text": "1000"},
                                "cbc:Name": {"_text": "IGV"},
                                "cbc:TaxTypeCode": {"_text": "VAT"},
                            },
                        },
                    },
                ],
            },
            "cac:LegalMonetaryTotal": {
                "cbc:LineExtensionAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": sub_total,
                },
                "cbc:TaxInclusiveAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": total,
                },
                "cbc:PayableAmount": {
                    "_attributes": {"currencyID": "PEN"},
                    "_text": total,
                },
            },
            "cac:InvoiceLine": item_list
        },
    }
    
    return ticket

