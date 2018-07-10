from django.conf        import settings
from golem_sci.factory  import new_concent_sci

from core.payments.storage import DatabaseTransactionsStorage

from web3 import Web3

class ConcentRPC:
    __instance = None

    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = new_concent_sci(
                DatabaseTransactionsStorage,
                settings.GETH_ADDRESS,
                Web3.toChecksumAddress(settings.CONCENT_ETHEREUM_ADDRESS),
                lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY)
            )
        return cls.__instance
