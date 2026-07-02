"""Purchasing module.

Manages suppliers, purchase requests, purchase orders and payments that feed
inventory. Suppliers are tenant-scoped; requests, orders and their payments are
branch-scoped (or tenant-scoped line items) following the binding multi-branch
data-model decision (see CLAUDE.md).
"""
