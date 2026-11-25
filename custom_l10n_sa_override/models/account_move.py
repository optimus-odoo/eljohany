from odoo.addons.l10n_sa_edi.models import account_move as sa_account_move

def patched_action_post(self):
    # Skip Saudi strict journal-company check
    return super(sa_account_move.AccountMove, self).action_post()

# Monkey patching the method
sa_account_move.AccountMove.action_post = patched_action_post
