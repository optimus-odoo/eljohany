# POS Order Customer Notes

Implementation task owner: **Ali Elsharkawy (علي الشرقاوي)**.

Shows the standard `pos.order.line.customer_note` values in the POS order
backend without modifying sales data:

- each line note is visible in the order-lines table;
- all non-empty line notes are shown together on the order form;
- the same notes are shown in one column on the POS order list;
- orders without customer notes remain blank and do not show the form summary.
