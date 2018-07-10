from django.conf.urls import url

from .views import send, receive, receive_out_of_band, protocol_constants, multiprocess_test_view

urlpatterns = [
    url(r'^multiprocess_test_view/$',                 multiprocess_test_view,                name = 'multiprocess_test_view'),
    url(r'^send/$',                 send,                name = 'send'),
    url(r'^receive/$',              receive,             name = 'receive'),
    url(r'^receive-out-of-band/$',  receive_out_of_band, name = 'receive_out_of_band'),
    url(r'^protocol-constants/$',   protocol_constants,  name = 'protocol_constants'),
]
