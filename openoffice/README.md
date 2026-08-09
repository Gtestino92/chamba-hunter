# Chamba Hunter OpenOffice actions

`chamba-openoffice-actions-installer.ods` installs or updates the module:

```text
My Macros -> Standard -> ChambaHunterActions
```

The `Standard` application library is used deliberately because Apache OpenOffice loads it automatically.

Installation/update:

1. keep the Chamba Hunter repository root configured as a trusted OpenOffice macro location;
2. open `openoffice/chamba-openoffice-actions-installer.ods` in Calc;
3. click `INSTALL / UPDATE CHAMBA ACTIONS`;
4. click `PING` to verify the global macro;
5. close and reopen OpenOffice after a first-time install if needed.

`PING` is non-destructive. `MarkApplied` is invoked only by generated shortlist `APPLY` links and delegates the DB write to the Chamba Hunter Python command.
