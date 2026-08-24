# Context and scope

This section covers the context and scope of the system. The MCP server will
be used by an agent like Hermes to manage the shopping list at Albert Heijn.

## Scope

The happie MCP server is the system under design. It exposes the product
assortment, the shopping list, and the ordering history of Albert Heijn as MCP
tools. It never completes a purchase order; the user remains in control of what
is actually bought.

## Business context

```mermaid
C4Context
    title Business context of the happie MCP server

    Person(user, "User", "Wants a shopping list for the coming week's groceries.")

    System_Boundary(home, "Home setup") {
        System_Ext(hermes, "Hermes", "Agent that talks to the user and composes the weekly shopping list.")
        System_Ext(qwen, "Qwen 3.8", "Locally hosted language model that powers Hermes' reasoning.")
        System(happie, "happie MCP server", "Exposes the Albert Heijn assortment, shopping list, and ordering history as MCP tools.")
    }

    System_Ext(ah, "Albert Heijn", "Grocery store that owns the product assortment, the shopping list, and the ordering history.")

    Rel(user, hermes, "Discusses the meals and groceries for next week")
    Rel(hermes, user, "Proposes and confirms the shopping list")
    Rel(hermes, qwen, "Interprets the conversation and decides on products")
    Rel(hermes, happie, "Searches products, reviews past purchases, and updates the shopping list")
    Rel(happie, ah, "Reads the assortment and ordering history, and maintains the shopping list")
    Rel(user, ah, "Reviews the shopping list and completes the purchase")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

### Domain interfaces

| Partner               | Direction | What is exchanged                                                                                   |
| --------------------- | --------- | --------------------------------------------------------------------------------------------------- |
| User ↔ Hermes         | both      | Meal plans and grocery wishes going in, a proposed shopping list coming back for confirmation.      |
| Hermes → Qwen 3.8     | outgoing  | The conversation and the tool results, so the model can decide which products belong on the list.   |
| Hermes → happie       | outgoing  | Product searches, requests for past purchases, and additions to or removals from the shopping list. |
| happie ↔ Albert Heijn | both      | Product assortment and ordering history coming in, shopping list changes going out.                 |
| User → Albert Heijn   | outgoing  | The final review and the actual purchase, which happens outside this system.                        |

The system deliberately has no interface for placing an order. Completing a
purchase stays a manual step performed by the user at Albert Heijn.
