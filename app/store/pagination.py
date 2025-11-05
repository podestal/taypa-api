from rest_framework.pagination import PageNumberPagination

"""
    Pagination for the Notaria app.
    This file defines a simple pagination for the Store app.
"""


class SimplePagination(PageNumberPagination):
    """
    Pagination class for the Kardex viewset.
    This class defines the pagination for the Kardex viewset.
    It uses page number pagination.
    """
    page_size = 10
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = 100
