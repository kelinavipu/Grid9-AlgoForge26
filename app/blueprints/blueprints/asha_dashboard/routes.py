"""
ASHA Dashboard Routes

Renders HTML pages for ASHA worker interface using Jinja2 templates.
Consumes data from /asha API endpoints.
"""

from flask import Blueprint, render_template, request, redirect, url_for
from app.repositories import asha_repo

asha_dashboard_bp = Blueprint('asha_dashboard', __name__, url_prefix='/asha/dashboard')


@asha_dashboard_bp.route('/')
def dashboard():
    """Main ASHA dashboard with summary statistics"""
    # Get ASHA ID from query parameter (no auth system)
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/dashboard.html', asha_id=asha_id, asha_name=asha_name)


@asha_dashboard_bp.route('/mothers')
def mothers():
    """My mothers page - list of assigned mothers"""
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/mothers.html', asha_id=asha_id, asha_name=asha_name)


@asha_dashboard_bp.route('/new-assessment')
def new_assessment():
    """New assessment form page"""
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/new_assessment.html', asha_id=asha_id, asha_name=asha_name)


@asha_dashboard_bp.route('/stats')
def stats():
    """My statistics page"""
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/stats.html', asha_id=asha_id, asha_name=asha_name)


@asha_dashboard_bp.route('/documents')
def view_documents():
    """View medical documents for a mother"""
    asha_id = request.args.get('asha_id', '')
    mother_id = request.args.get('mother_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/view_documents.html', 
                         asha_id=asha_id, 
                         asha_name=asha_name,
                         mother_id=mother_id)


@asha_dashboard_bp.route('/notifications')
def notifications():
    """View notifications and messages from doctors"""
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/notifications.html', 
                         asha_id=asha_id, 
                         asha_name=asha_name)


@asha_dashboard_bp.route('/ai-assistant')
def rag_chatbot():
    """ASHA RAG AI Assistant chatbot interface"""
    asha_id = request.args.get('asha_id', '')
    
    # Get ASHA name
    asha_name = ''
    if asha_id:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    
    return render_template('asha/rag_chatbot.html', 
                         asha_id=asha_id, 
                         asha_name=asha_name)

