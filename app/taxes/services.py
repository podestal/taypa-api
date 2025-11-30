"""
Service module for Sunat document processing
Handles XML downloading, unzipping, and parsing
"""
import requests
import zipfile
import io
from typing import Dict, Optional, Tuple, List
from defusedxml import ElementTree as ET
from django.conf import settings


def download_and_extract_xml(xml_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Download zip file from XML URL, extract and return XML content as string
    
    Args:
        xml_url: URL to the zip file containing the XML
        
    Returns:
        Tuple of (XML content as string, error message). 
        If successful: (xml_content, None)
        If error: (None, error_message)
    """
    try:
        # Download the zip file
        response = requests.get(xml_url, timeout=30)
        response.raise_for_status()
        
        # Check if response is actually a zip file
        content_type = response.headers.get('Content-Type', '').lower()
        if 'zip' not in content_type and not xml_url.endswith('.zip'):
            # Might be XML directly, try to parse it
            try:
                content = response.text
                # Try to parse as XML to validate
                ET.fromstring(content)
                return content, None
            except:
                pass
        
        # Read zip file from memory
        zip_data = io.BytesIO(response.content)
        
        # Extract XML from zip
        try:
            with zipfile.ZipFile(zip_data, 'r') as zip_ref:
                # Get list of files in zip
                file_list = zip_ref.namelist()
                
                if not file_list:
                    return None, "Zip archive is empty"
                
                # Find XML file (usually ends with .xml or .XML - case insensitive)
                xml_file = None
                for file_name in file_list:
                    if file_name.lower().endswith('.xml'):
                        xml_file = file_name
                        break
                
                if not xml_file:
                    return None, f"No XML file found in zip archive. Files: {', '.join(file_list)}"
                
                # Read XML content
                xml_content = zip_ref.read(xml_file)
                return xml_content.decode('utf-8'), None
        except zipfile.BadZipFile:
            # Maybe it's not a zip, try to parse as XML directly
            try:
                content = response.text
                ET.fromstring(content)
                return content, None
            except Exception as e:
                return None, f"Invalid zip file or XML format: {str(e)}"
            
    except requests.exceptions.Timeout:
        return None, f"Timeout downloading XML from {xml_url}"
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error {e.response.status_code} downloading XML: {str(e)}"
    except requests.exceptions.RequestException as e:
        return None, f"Request error downloading XML: {str(e)}"
    except Exception as e:
        return None, f"Error downloading/extracting XML: {str(e)}"


def parse_xml_serie_numero(xml_content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse XML content to extract serie and numero
    
    Args:
        xml_content: XML content as string
        
    Returns:
        Tuple of (serie, numero) or (None, None) if not found
    """
    try:
        root = ET.fromstring(xml_content)
        
        # Define namespaces (UBL 2.1 standard)
        namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        }
        
        # Try to find ID element which contains serie-numero
        # Path: Invoice/cbc:ID or CreditNote/cbc:ID
        id_elem = root.find('.//cbc:ID', namespaces)
        
        if id_elem is not None and id_elem.text:
            # Format is usually "B001-00000001" or "F001-00000001"
            id_text = id_elem.text.strip()
            if '-' in id_text:
                parts = id_text.split('-', 1)
                return parts[0], parts[1]
        
        # Try without namespace
        id_elem = root.find('.//ID')
        if id_elem is not None and id_elem.text:
            id_text = id_elem.text.strip()
            if '-' in id_text:
                parts = id_text.split('-', 1)
                return parts[0], parts[1]
        
        return None, None
        
    except Exception as e:
        print(f"Error parsing XML for serie/numero: {str(e)}")
        return None, None


def parse_xml_amount(xml_content: str) -> Optional[float]:
    """
    Parse XML content to extract total amount (InvoiceTotalAmount)
    
    Args:
        xml_content: XML content as string
        
    Returns:
        Total amount as float, or None if not found
    """
    try:
        # Parse XML using defusedxml (safe XML parser)
        root = ET.fromstring(xml_content)
        
        # Define namespaces (UBL 2.1 standard for Peruvian invoices)
        namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        }
        
        # Try to find InvoiceTotalAmount or LegalMonetaryTotal
        # Path: Invoice/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount
        # or: Invoice/cac:LegalMonetaryTotal/cbc:PayableAmount
        
        # First try TaxInclusiveAmount (amount with taxes)
        amount_elem = root.find('.//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount', namespaces)
        
        if amount_elem is None:
            # Fallback to PayableAmount
            amount_elem = root.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', namespaces)
        
        if amount_elem is not None and amount_elem.text:
            return float(amount_elem.text)
        
        # Alternative: try without namespace prefix (some XMLs might not use namespaces properly)
        amount_elem = root.find('.//TaxInclusiveAmount')
        if amount_elem is None:
            amount_elem = root.find('.//PayableAmount')
        
        if amount_elem is not None and amount_elem.text:
            return float(amount_elem.text)
        
        return None
        
    except Exception as e:
        print(f"Error parsing XML for amount: {str(e)}")
        return None


def process_sunat_document(sunat_doc: Dict) -> Dict:
    """
    Process a single Sunat document: download XML and extract amount, serie, numero
    
    Args:
        sunat_doc: Document dict from Sunat API response
        
    Returns:
        Dict with processed data including amount, serie, numero
    """
    result = {
        'amount': None,
        'serie': None,
        'numero': None,
        'xml_processed': False,
        'error': None
    }
    
    xml_url = sunat_doc.get('xml')
    if not xml_url:
        result['error'] = 'No XML URL in document'
        return result
    
    # Download and extract XML
    xml_content, error = download_and_extract_xml(xml_url)
    if not xml_content:
        result['error'] = error or 'Failed to download/extract XML'
        return result
    
    # Parse amount from XML
    amount = parse_xml_amount(xml_content)
    result['amount'] = amount
    
    # Parse serie and numero from XML (if not already in sunat_doc)
    if not sunat_doc.get('serie') or not sunat_doc.get('numero'):
        serie, numero = parse_xml_serie_numero(xml_content)
        if serie:
            result['serie'] = serie
        if numero:
            result['numero'] = numero
    
    result['xml_processed'] = True
    
    return result


def parse_xml_invoice_lines(xml_content: str) -> List[Dict]:
    """
    Parse XML content to extract invoice lines (order items)
    
    Args:
        xml_content: XML content as string
    
    Returns:
        List of items with 'name', 'quantity', 'cost'
    """
    try:
        root = ET.fromstring(xml_content)
        
        # Define namespaces (UBL 2.1 standard)
        namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        }
        
        items = []
        
        # Find all InvoiceLine elements
        invoice_lines = root.findall('.//cac:InvoiceLine', namespaces)
        
        for line in invoice_lines:
            # Get quantity
            quantity_elem = line.find('.//cbc:InvoicedQuantity', namespaces)
            quantity = float(quantity_elem.text) if quantity_elem is not None and quantity_elem.text else 1.0
            
            # Get item description
            description_elem = line.find('.//cbc:Description', namespaces)
            name = description_elem.text.strip() if description_elem is not None and description_elem.text else "Item"
            
            # Get price per unit (without tax)
            price_elem = line.find('.//cac:Price/cbc:PriceAmount', namespaces)
            if price_elem is not None and price_elem.text:
                unit_price = float(price_elem.text)
            else:
                # Try to get line extension amount and divide by quantity
                line_extension_elem = line.find('.//cbc:LineExtensionAmount', namespaces)
                if line_extension_elem is not None and line_extension_elem.text:
                    line_amount = float(line_extension_elem.text)
                    unit_price = line_amount / quantity if quantity > 0 else 0.0
                else:
                    unit_price = 0.0
            
            items.append({
                'id': str(len(items) + 1),
                'name': name,
                'quantity': quantity,
                'cost': unit_price,
            })
        
        return items
        
    except Exception as e:
        print(f"Error parsing XML for invoice lines: {str(e)}")
        return []


def parse_xml_customer_info(xml_content: str) -> Dict[str, Optional[str]]:
    """
    Parse XML content to extract customer info (for facturas)
    
    Args:
        xml_content: XML content as string
    
    Returns:
        Dict with 'razon_social', 'ruc', 'address' or None values if not found
    """
    result = {
        'razon_social': None,
        'ruc': None,
        'address': None
    }
    
    try:
        root = ET.fromstring(xml_content)
        
        # Define namespaces (UBL 2.1 standard)
        namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        }
        
        # Find Customer/AccountingCustomerParty
        # Path: Invoice/cac:AccountingCustomerParty/cac:Party
        customer_party = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces)
        
        if customer_party is not None:
            # Get RUC from PartyIdentification/ID
            party_id = customer_party.find('.//cac:PartyIdentification/cbc:ID', namespaces)
            if party_id is not None and party_id.text:
                result['ruc'] = party_id.text.strip()
            
            # Get razon_social from PartyLegalEntity/RegistrationName
            registration_name = customer_party.find('.//cac:PartyLegalEntity/cbc:RegistrationName', namespaces)
            if registration_name is not None and registration_name.text:
                result['razon_social'] = registration_name.text.strip()
            
            # Get address from PartyLegalEntity/RegistrationAddress/AddressLine/Line
            address_line = customer_party.find('.//cac:PartyLegalEntity/cac:RegistrationAddress/cac:AddressLine/cbc:Line', namespaces)
            if address_line is not None and address_line.text:
                result['address'] = address_line.text.strip()
        
        return result
        
    except Exception as e:
        print(f"Error parsing XML for customer info: {str(e)}")
        return result

