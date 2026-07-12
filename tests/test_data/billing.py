def get_invoice(request):
    invoice_id = request.args.get("id")
    if not invoice_id:
        abort(400, "Invoice ID required")
    db = get_db_connection()
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        abort(404, "Invoice not found")
    # IDOR fix: ensure the authenticated user owns this invoice
    current_user_id = session.get('user_id')
    if not current_user_id:
        abort(401, "Authentication required")
    if invoice.user_id != current_user_id:
        abort(403, "Access denied")
    return invoice.to_json()
