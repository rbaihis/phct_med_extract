{
    'name': 'PHCT Circulaire (Importer)',
    'version': '1.1.0',
    'summary': 'Fetch and store PHCT circulaires using existing parser',
    'category': 'Tools',
    'author': 'Migration Bot',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/phct_circulaire_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
}
