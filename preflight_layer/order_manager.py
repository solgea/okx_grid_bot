import logging

from preflight_layer.domain import ExecutionAuthorization
from preflight_layer.validator import PreFlightValidator

logger = logging.getLogger("OrderManager")


class OrderManager:
    def __init__(self, adapter, validator: PreFlightValidator):
        self.adapter = adapter
        self.validator = validator

    def authorize_intents(self, intents, metadata, account, market):
        """Validate intents and issue a fail-closed execution authorization."""
        accepted, rejected = self.validator.validate_batch(
            intents, metadata, account, market
        )
        for intent, result in rejected:
            logger.warning(
                "PreFlight emri filtreledi: instrument=%s code=%s",
                intent.instrument_id,
                result.rejection_code,
            )

        authorization = ExecutionAuthorization.from_authorized_intents(accepted)
        if rejected and not accepted:
            first_rejection = rejected[0][1]
            authorization = ExecutionAuthorization.rejected(
                first_rejection.message or "All intents rejected by PreFlight.",
                first_rejection.rejection_code,
            )
        return accepted, authorization

    def validate_intents(self, intents, metadata, account, market):
        """Deprecated compatibility shim. Execution must use authorize_intents.

        Kept only for unmerged branches that still call this name; it discards
        the authorization token, so it cannot be used to reach execution.
        """
        accepted, _ = self.authorize_intents(intents, metadata, account, market)
        return accepted

    async def authorize_intent(self, intent, adapter=None):
        """Authorize a single intent, pulling fresh state from the adapter.

        Returns (accepted, authorization). The authorization token is the only
        way to reach execution; this method never places an order itself.
        """
        source = adapter or self.adapter
        metadata = await source.fetch_instrument_metadata(intent.instrument_id)
        account = await source.fetch_account_state()
        market = await source.fetch_market_data(intent.instrument_id)

        accepted, authorization = self.authorize_intents(
            [intent], metadata, account, market
        )
        if not accepted:
            logger.warning(
                "Order intent rejected by PreFlight: %s - %s",
                authorization.rejection_code,
                authorization.message,
            )
        return bool(accepted), authorization
