"""
Utility functions for syncing documents from Sunat API
"""
from typing import List, Dict, Tuple
from django.utils import timezone

from .models import Document


def process_and_sync_documents(sunat_documents: List[Dict], process_sunat_document_func) -> Tuple[int, List[Dict]]:
    """
    Process and sync documents to database.
    
    Args:
        sunat_documents: List of document dictionaries from Sunat API
        process_sunat_document_func: Function to process sunat documents (passed in for testability)
        
    Returns:
        Tuple of (synced_count, errors_list)
    """
    synced_count = 0
    errors = []
    
    # Process each document
    for sunat_doc in sunat_documents:
        try:
            # Process XML to extract amount (this may fail, but we still want to save the document)
            processed_data = process_sunat_document_func(sunat_doc)
            
            # Sync to database even if XML processing failed
            # This way we at least have the basic document info
            document = Document.sync_from_sunat(sunat_doc, processed_data)
            
            if document:
                synced_count += 1
                # Print serie and numero of synced document
                print(f"✓ Synced: {document.serie}-{document.numero} (Type: {document.document_type}, Amount: {document.amount})")
                # Only report error if XML processing failed
                if processed_data.get('error'):
                    errors.append({
                        'sunat_id': sunat_doc.get('id'),
                        'xml_url': sunat_doc.get('xml'),
                        'error': processed_data['error']
                    })
        
        except Exception as e:
            errors.append({
                'sunat_id': sunat_doc.get('id', 'unknown'),
                'xml_url': sunat_doc.get('xml'),
                'error': str(e)
            })
    
    return synced_count, errors


def filter_today_documents(sunat_documents: List[Dict]) -> List[Dict]:
    """
    Filter documents to only include those created today in our database.
    
    Includes:
    - Documents in DB that were created today (based on created_at field)
    - New documents not in DB yet (to sync them for the first time)
    
    Args:
        sunat_documents: List of document dictionaries from Sunat API
        
    Returns:
        List of documents created today (based on created_at) or new documents
    """
    now = timezone.now()
    
    # Get all existing document IDs from our database (created today based on created_at)
    existing_today_doc_ids = set(
        Document.objects.filter(
            created_at__date=now.date()
        ).values_list('sunat_id', flat=True)
    )
    
    # Get all existing document IDs from our database (any date)
    all_existing_doc_ids = set(
        Document.objects.values_list('sunat_id', flat=True)
    )
    
    # Filter documents based on created_at date, not Sunat's issueTime
    today_documents = []
    
    for doc in sunat_documents:
        doc_id = doc.get('id')
        
        # Include documents that exist in our DB and were created today
        # (based on created_at field, not sunat_issue_time)
        if doc_id and doc_id in existing_today_doc_ids:
            today_documents.append(doc)
        # Also include new documents not in our DB yet (to sync them for the first time)
        elif doc_id and doc_id not in all_existing_doc_ids:
            today_documents.append(doc)
    
    return today_documents

