## Module <ohrms_loan>

#### 18.11.2026
#### Version 17.0.2.1.0
##### ADD

- Allow a new loan request after six calendar months from the latest approved
  loan request even when its balance is still outstanding.
- Recheck eligibility on request creation, submission, and final approval;
  final approvals for the same employee are serialized to prevent concurrent
  requests from bypassing the rule.
- Keep fully settled loans immediately eligible and show the exact next
  eligible date when an unpaid loan is still inside the waiting period.

#### 28.11.2023
#### Version 17.0.1.0.0
##### ADD

- Initial commit for Open HRMS Loan Management

##### FIX 

- Updated the Loan Smart button view and added the domain for the tree and form view
