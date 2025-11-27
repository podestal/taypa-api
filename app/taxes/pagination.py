from rest_framework.pagination import PageNumberPagination

"""
Pagination for the Taxes app.
This file defines the pagination for the Taxes app.
"""


class SimplePagination(PageNumberPagination):
    """
    Simple pagination class for the Taxes app.
    This class defines the pagination for the Taxes app.
    It uses page number pagination.
    """
    page_size = 10
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = 100
