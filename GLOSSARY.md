# Kosha Financial

The banking domain behind LedgerLens MCP: a fictional Indian digital bank that serves retail customers through a partner-bank model and gives its staff AI agents that read customer, payment, risk and policy information.

## Parties

**Customer**:
A person or sole proprietor who holds one or more Accounts with Kosha, identified by a CIF number.
_Avoid_: User, client, account holder

**CIF number**:
The bank's permanent 10-digit identifier for a Customer (Customer Information File), stable across all their Accounts.
_Avoid_: Customer number, customer ID (when meaning the bank-facing number)

**Persona**:
The behavioural archetype a Customer belongs to (salaried, student, gig worker, SME owner, NRI, senior citizen), which shapes their spending and income patterns.
_Avoid_: Segment (a different concept)

**Segment**:
The commercial tier a Customer is served in (mass, affluent, premium).
_Avoid_: Persona, tier

**Staff member**:
A Kosha employee who acts through an agent, holding exactly one Role.
_Avoid_: User, operator, agent (an agent is software)

**Role**:
The job function a Staff member performs — support agent, analyst, compliance officer, or demo viewer — which determines what they may see and do.
_Avoid_: Permission, group

## Accounts and money

**Account**:
A deposit relationship (savings, salary, current, fixed or recurring deposit) owned by one Customer.
_Avoid_: Wallet, profile

**Ledger balance**:
The balance implied by every posted entry on an Account.
_Avoid_: Balance (ambiguous)

**Available balance**:
Ledger balance minus Holds — what the Customer can spend right now.
_Avoid_: Usable balance, free balance

**Hold**:
An amount on an Account earmarked and unavailable for spending, pending an outcome.
_Avoid_: Block (used for cards)

**Lien**:
A legally enforceable claim marked on an Account balance, typically under a court or regulator order.
_Avoid_: Hold

**Freeze**:
A restriction on an Account: a debit freeze stops money leaving, a credit freeze stops money arriving, a total freeze stops both.
_Avoid_: Block, lock

**Dormant account**:
An Account with no Customer-initiated activity for 12 months, flagged for reactivation outreach.
_Avoid_: Inactive account

**Inoperative account**:
An Account with no Customer-initiated activity for 24 months, which per RBI rules requires re-KYC before it can be operated again.
_Avoid_: Dormant account (a different threshold)

**Journal entry**:
A balanced set of Postings recording one economic event.
_Avoid_: Ledger entry, booking

**Posting**:
A single signed amount against one ledger account within a Journal entry; the Postings of an entry always sum to zero.
_Avoid_: Line item, leg

**GL account**:
A general-ledger account that Postings land in: `customer_deposits`, whose sub-ledgers are the Customers' Accounts, or an internal account such as a rail's settlement account, fee income, GST payable, suspense or opening balances (balances brought forward from before the ledger went live).
_Avoid_: Ledger (the whole book), nostro (a different concept)

## Payments

**Transaction**:
A single movement of money into or out of an Account through one Rail, with its own lifecycle.
_Avoid_: Payment (a customer-intent concept), transfer

**Rail**:
The payment network a Transaction travels on: UPI, IMPS, NEFT, RTGS, card, ATM, NACH or internal.
_Avoid_: Channel (a different concept), method

**Channel**:
The touchpoint where a Transaction was initiated: mobile app, web, POS terminal, ATM or API.
_Avoid_: Rail, source

**VPA**:
A UPI virtual payment address such as `name@kosha` that routes to an Account.
_Avoid_: UPI ID, handle

**UTR**:
The unique reference a clearing network assigns to an IMPS, NEFT or RTGS Transaction.
_Avoid_: Reference number (ambiguous)

**RRN**:
The 12-digit retrieval reference number identifying a UPI or card Transaction.
_Avoid_: Reference number (ambiguous)

**Beneficiary**:
A saved payee Account a Customer can send money to, subject to a Cooling period after it is added.
_Avoid_: Payee, recipient

**Cooling period**:
The window after a Beneficiary is added during which transfers to it are capped, to blunt account-takeover fraud.
_Avoid_: Grace period

**Credit delayed**:
A Transaction state where the Customer's Account is debited but the beneficiary bank has not yet credited the recipient.
_Avoid_: Stuck payment, pending (too broad)

**Deemed success**:
A UPI Transaction treated as successful because the beneficiary bank timed out after the network approved it, pending later confirmation or reversal.
_Avoid_: Assumed success

**Reversal**:
The return of a debited amount to the Customer's Account after a Transaction fails downstream.
_Avoid_: Refund (merchant-initiated), chargeback

**Refund**:
A merchant-initiated return of money for a completed purchase.
_Avoid_: Reversal

**TAT**:
The regulator-mandated turnaround time within which a failed Transaction must be resolved, beyond which the Customer is owed compensation.
_Avoid_: SLA (internal targets)

## Know your customer

**KYC profile**:
The record of how a Customer's identity was verified, its current KYC status and when it must next be reviewed.
_Avoid_: KYC (alone), verification

**Min-KYC**:
A limited verification level permitting restricted Account usage until Full KYC is completed.
_Avoid_: Basic KYC, small account

**Full KYC**:
Complete identity and address verification permitting unrestricted Account usage.
_Avoid_: Complete KYC

**V-CIP**:
Video-based Customer Identification Process: live video verification by a trained Kosha official.
_Avoid_: Video KYC (informal)

**OVD**:
An Officially Valid Document accepted as proof of identity or address under the RBI KYC Master Direction.
_Avoid_: ID proof

**CKYC number**:
The 14-digit identifier (KIN) a Customer holds in the Central KYC Registry.
_Avoid_: KIN (alone), CKYC ID

**Re-KYC**:
The periodic refresh of a KYC profile, due every 2, 8 or 10 years for high, medium or low risk Customers.
_Avoid_: KYC renewal, re-verification

**Risk category**:
The money-laundering risk rating (low, medium, high) assigned to a Customer, which drives Re-KYC frequency and monitoring depth.
_Avoid_: Risk score (a per-Transaction number)

## Financial crime

**PEP**:
A Politically Exposed Person, or a close associate or relative of one, requiring enhanced due diligence.
_Avoid_: VIP

**Screening**:
Checking a name against sanctions and PEP lists, producing clear, potential match or true match.
_Avoid_: Background check, name check

**AML alert**:
A signal raised when a Customer's activity matches a Typology rule, to be investigated and dispositioned by an analyst.
_Avoid_: Flag, case

**Typology**:
A recognised money-laundering or fraud pattern, such as structuring, mule account or round-tripping.
_Avoid_: Scenario, rule (a rule detects a typology)

**Mule account**:
An Account used to receive and rapidly pass on illicit funds on behalf of others.
_Avoid_: Money mule (refers to the person)

**STR**:
A Suspicious Transaction Report filed with FIU-IND when an investigation concludes activity is suspicious.
_Avoid_: SAR (US term)

**CTR**:
A Cash Transaction Report filed with FIU-IND for cash activity above the reporting threshold.
_Avoid_: Large cash report

**Transaction review**:
A request, raised by a Staff member, that a specific Transaction be examined by the risk team.
_Avoid_: Flag, alert

**Dispute**:
A Customer's formal challenge to a Transaction, tracked to resolution within TAT.
_Avoid_: Complaint (broader), ticket

**Chargeback**:
The card-network process of reclaiming a disputed card Transaction from the merchant's bank.
_Avoid_: Reversal, refund

## Knowledge

**SOP**:
A Standard Operating Procedure: the step-by-step way a Department performs a recurring task.
_Avoid_: Process doc, guide

**Policy**:
A board- or management-approved statement of rules that SOPs implement.
_Avoid_: SOP, guideline

**Document**:
Any controlled knowledge artefact — Policy, SOP, runbook, playbook, API reference, FAQ or template — with a code, version, owner and effective date.
_Avoid_: File, article, page

**Department**:
The organisational unit that owns a Document: Compliance, Onboarding, Legal, Risk & Fraud, Customer Support, Sales, Marketing, Engineering or Corporate.
_Avoid_: Team, function

**Classification**:
A Document's sensitivity — public, internal, confidential or restricted — bounding which Roles may read it.
_Avoid_: Visibility, access level

**Effective version**:
The single version of a Document currently in force; earlier versions are superseded.
_Avoid_: Latest version (a draft can be later)
