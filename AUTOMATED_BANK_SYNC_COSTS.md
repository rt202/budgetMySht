# Automated Bank Sync Costs

Goal: automate transaction imports for one Chase login that includes a checking account and a credit card, while keeping recurring data-access costs under about $30/year.

## Recommendation

For a personal budgeting app with a hard cost ceiling, prefer SimpleFIN Bridge first if it supports the Chase accounts reliably enough. Its public pricing is $1.50/month or $15/year, which stays under the $30/year target.

Plaid and Teller are better-known developer APIs and may be convenient, but their long-term cost and account status should be verified before depending on them:

- Plaid: good Chase support and free/small trial options, but exact Pay-as-you-go prices are shown inside the Plaid Dashboard before submitting a Production request.
- Teller: public Transactions pricing is $0.30 per enrollment per month in Production, and its developer environment allows real bank data with up to 100 enrollments for free. Production access may require business verification.

For one Chase login, checking plus credit card should generally be treated as one connection/enrollment/item, not two separate bank connections.

## Cost Resources

- Plaid pricing: https://plaid.com/pricing
- Plaid billing details: https://plaid.com/docs/account/billing/
- Plaid Transactions: https://plaid.com/docs/transactions/
- SimpleFIN Bridge pricing: https://bridge.simplefin.org/
- SimpleFIN developer guide: https://beta-bridge.simplefin.org/info/developers
- Teller pricing: https://teller.io/
- Teller environments: https://teller.io/docs/guides/environments

## Stop-Charge Checklist

### Plaid

Plaid subscription-billed products such as Transactions can continue billing while a valid access token exists. To stop billing, remove the Item with Plaid's `/item/remove` endpoint. The user can also depermission the connection at https://my.plaid.com/.

Also check:

- Usage: https://dashboard.plaid.com/activity/usage
- Billing settings: https://dashboard.plaid.com/settings/team/billing
- Plans: https://dashboard.plaid.com/settings/team/plans
- Products: https://dashboard.plaid.com/settings/team/products

Important Plaid note: if an Item has a subscription product like Transactions, Plaid says billing can continue even if no API calls are made. Removing the Item is the key step.

### SimpleFIN Bridge

The user can disable the app's access token at any point. If using the paid Bridge subscription, also cancel or manage the Bridge subscription from the SimpleFIN Bridge account interface.

This app exposes three escalating ways to stop SimpleFIN-related charges and access:

1. **Stop the daily background sync only.** Run `bash scripts/uninstall_launchd.sh`. Manual syncs from the Load Data button still work.
2. **Stop this app's access entirely without canceling SimpleFIN.** Open the in-app Settings page and click **Disconnect SimpleFIN**, then disable the access token at https://bridge.simplefin.org/. The Bridge subscription continues so other linked apps still work.
3. **Cancel the SimpleFIN Bridge subscription.** Log in to https://bridge.simplefin.org/ and cancel the subscription. After cancellation, no further `$1.50/month` or `$15/year` charges occur. This is the only step that fully stops the recurring charge.

### Teller

If using Teller Production, stop using the Transactions enrollment and confirm in Teller's dashboard/support flow that the enrollment is removed or no longer billable. Teller's public pricing says Transactions are billed per enrollment per month.

## Implementation Guardrails

- Store provider access tokens in one place so connections can be removed cleanly.
- Add a "disconnect bank sync" command or script before relying on a paid provider.
- Avoid paid products that are unnecessary for budgeting. Transaction history is the core need; identity, auth, transfers, statements, and underwriting products should stay disabled unless explicitly needed.
- Check dashboard usage monthly while testing.
