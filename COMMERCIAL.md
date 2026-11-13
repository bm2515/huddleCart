# How HuddleCart creates economic value

## The problem we saw in Round 1
Our test run in one building: **$167 in orders, 8 customers, 37 items, $26 profit**. Every small order would have paid **$5 shipping** on its own. The leader spent most of the time matching items to buyers by hand and messaging each person.

## Who gains, per pod order (8 neighbors)

| Who | Before | With HuddleCart |
|---|---|---|
| Neighbor | $5 shipping, or skips the order | $2 pod fee, so **$3 saved** each time |
| Leader | Hours of matching items and chasing payments | One tap to lock, one tap for "arrived". Bags, amounts and Venmo links are made for them. Keeps a share of the pod fees. |
| Building | 8 deliveries | 1 delivery |
| Retailer (Weee, Amazon Fresh) | 8 small baskets, often abandoned under the minimum | One basket above the free-shipping minimum |

## How the money works
- 8 neighbors x $2 fee = **$16 per pod order**, split between the leader and HuddleCart.
- AI cost per pod order: about 40 agent messages x $0.0006 (Flash-Lite, see `agent/evals/EVALS.md`) = **about $0.03**. That leaves almost all of the fee as margin.
- Later revenue: retailer affiliate or partner fees on the combined basket, and sponsored pods for events (Diwali, birthdays, Halloween).

## Why it keeps growing
- **Community loop:** XP, streaks, badges and the shared free-shipping quest turn one order into a weekly habit. Each new member makes the minimum easier to reach for everyone else.
- **Low cost to start:** a pod is just a channel in a building. There's no warehouse and no drivers, because the retailer delivers and the leader hands out the bags.
- **Measured savings:** the leaderboard shows the building's total shipping saved, which is our pitch to the next building.

## What it costs us
- Gemini API: about $0.06 per 100 agent messages on the fast tier.
- Tavily search, LangSmith tracing, and Vercel hosting, all on free or starter tiers at prototype scale.
