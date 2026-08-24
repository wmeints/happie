# Introduction and goals

## Goal 

This MCP server provides access to the Albert Heijn API so we can automatically
manage the shopping list for our weekly grocery shopping. 

## Requirements overview

1. Provide access to the product assortment so we can choose products to put 
   on the shopping list.

2. Provide access to the shopping list to put products on it we want to 
   purchase. 

3. Provide access to the ordering history to retrieve past purchases so we can
   optimize the shopping list.

## Quality goals

1. The MCP server only provides access to methods that don't involve actually 
   completing purchase orders so a human still has the final say in what is 
   purchased.

2. The credentials used by the MCP server are stored in a safe location in the
   user profile that is only user-readable.
