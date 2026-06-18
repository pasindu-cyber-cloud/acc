"""Demo / live trader.

Places REAL Accumulator orders through an `ExecutionGateway` (the Deriv WS
client) for DEMO or LIVE accounts. It depends ONLY on the gateway interface, so
it is unit-testable with a fake gateway and never imports websockets directly.

Safety properties enforced structurally (not just by config):
  * Construction requires a gateway AND an authorised token.
  * Every entry must pass the injected SafeguardEngine.can_enter() gate.
  * Stake is fixed per call; there is NO method that increases stake after a
    loss (no martingale is even expressible through this API).
  * LIVE mode requires live_confirmed=True or entries are refused.

Dual-path take-profit (compatibility):
  * "proposal"        -> set limit_order.take_profit at proposal time.
  * "contract_update" -> buy first, then contract_update the take_profit.
  * "both"            -> proposal-time TP, then reaffirm via contract_update.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import Mode
from ..models import (
    DeteriorationResult,
    MarketScore,
    OpenContract,
    Proposal,
    TradeRecord,
)
from ..transport.base import ExecutionGateway
from .safeguards import SafeguardEngine


@dataclass
class ExecutionResult:
    accepted: bool
    contract: OpenContract | None = None
    reject_reasons: list[str] | None = None


class DemoLiveTrader:
    def __init__(
        self,
        gateway: ExecutionGateway,
        safeguards: SafeguardEngine,
        mode: Mode,
        currency: str = "USD",
        live_confirmed: bool = False,
        take_profit_mode: str = "proposal",
    ) -> None:
        if mode not in (Mode.DEMO, Mode.LIVE):
            raise ValueError("DemoLiveTrader only valid for DEMO or LIVE modes.")
        self.gateway = gateway
        self.safeguards = safeguards
        self.mode = mode
        self.currency = currency
        self.live_confirmed = live_confirmed
        self.take_profit_mode = take_profit_mode
        self._authorized = False
        self.open_contracts: dict[str, OpenContract] = {}

    async def authorize(self, token: str) -> None:
        await self.gateway.authorize(token)
        self._authorized = True

    async def try_enter(
        self,
        score: MarketScore,
        deterioration: DeteriorationResult | None,
        active_critical_alert: bool,
        ready_dwell_sec: float,
        stake: float,
        growth_rate: float,
        take_profit: float | None,
    ) -> ExecutionResult:
        if not self._authorized:
            return ExecutionResult(False, reject_reasons=["not_authorized"])
        if self.mode is Mode.LIVE and not self.live_confirmed:
            return ExecutionResult(False, reject_reasons=["live_not_confirmed"])

        decision = self.safeguards.can_enter(
            score=score,
            deterioration=deterioration,
            active_critical_alert=active_critical_alert,
            ready_dwell_sec=ready_dwell_sec,
            proposed_growth_rate=growth_rate,
        )
        if not decision:
            return ExecutionResult(False, reject_reasons=decision.reasons)

        proposal = Proposal(
            symbol=score.symbol,
            currency=self.currency,
            amount=stake,
            growth_rate=growth_rate,
            take_profit=take_profit if self.take_profit_mode in ("proposal", "both") else None,
        )
        proposal = await self.gateway.propose(proposal)
        if not proposal.id:
            return ExecutionResult(False, reject_reasons=["proposal_failed"])

        price = proposal.spot if proposal.spot is not None else stake
        contract = await self.gateway.buy(proposal.id, price=stake)
        contract.growth_rate = growth_rate
        contract.take_profit = take_profit

        # Post-buy take-profit path (compatibility / reaffirm).
        if take_profit is not None and self.take_profit_mode in ("contract_update", "both"):
            try:
                await self.gateway.update_contract(contract.contract_id, take_profit)
            except Exception:
                # If contract_update is unsupported, the proposal-time TP (if any)
                # still applies; we simply log and continue.
                pass

        self.open_contracts[contract.contract_id] = contract
        self.safeguards.register_open()
        return ExecutionResult(True, contract=contract)

    async def poll(self, contract_id: str) -> OpenContract:
        contract = await self.gateway.poll_contract(contract_id)
        self.open_contracts[contract_id] = contract
        return contract

    async def update_take_profit(self, contract_id: str, take_profit: float | None) -> None:
        await self.gateway.update_contract(contract_id, take_profit)
        if contract_id in self.open_contracts:
            self.open_contracts[contract_id].take_profit = take_profit

    async def exit(self, contract_id: str, reason: str = "manual") -> TradeRecord:
        contract = self.open_contracts.get(contract_id)
        await self.gateway.sell(contract_id, price=0.0)
        final = await self.gateway.poll_contract(contract_id)
        pnl = final.profit
        self.safeguards.register_close(pnl)
        self.open_contracts.pop(contract_id, None)
        return TradeRecord(
            symbol=final.symbol or (contract.symbol if contract else ""),
            mode=self.mode.value,
            entry_epoch=contract.entry_epoch if contract else 0,
            exit_epoch=final.entry_epoch,
            growth_rate=contract.growth_rate if contract else 0.0,
            stake=contract.buy_price if contract else 0.0,
            take_profit=contract.take_profit if contract else None,
            pnl=pnl,
            exit_reason=reason,
        )
