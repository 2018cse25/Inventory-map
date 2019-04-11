from flask import Flask, render_template, url_for, redirect, abort
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_sqlalchemy import SQLAlchemy
import psycopg2
from wtforms import validators, Form
import os

app = Flask(__name__)
app.config['demo'] = os.environ.get('IS_DEMO', False)
app.config['is_production'] = os.environ.get('IS_PRODUCTION', True)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '0012345679')
app.config['GA_TRACKING_ID'] = os.environ.get('GA_TRACKING_ID', None)

app.config['FLASK_ADMIN_SWATCH'] = os.environ.get('FLASK_ADMIN_SWATCH', 'lumen')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get( 'DATABASE_URL', 'postgresql://tester:pass123@localhost/inventory')
app.config['SQLALCHEMY_ECHO'] = not (app.config['is_production'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
db = SQLAlchemy(app)
engine = db.create_engine(app.config['SQLALCHEMY_DATABASE_URI'])

class ModelViewProduct(ModelView):
    can_delete = False
    can_view_details = True
    can_export = True
    export_types = ['csv', 'xls']
    column_labels = dict(name='Product Name',
                         description='Product Description')
    column_filters = ['id', 'name', 'description',
                      'time_created', 'time_updated']
    page_size = 20
    column_exclude_list = ['time_created', 'time_updated']
    column_searchable_list = ['name', 'description']
    column_editable_list = ['name', ]
    form_excluded_columns = ['time_created', 'time_updated']
    form_args = {
        'name': {
            'label': 'Product Name'
        },
        'description': {
            'label': 'Product Description'
        }
    }
    form_widget_args = {
        'description': {
            'rows': 10,
            'style': 'color: black'
        }
    }

class ModelViewLocation(ModelView):
    can_delete = False
    can_view_details = True
    can_export = True
    export_types = ['csv', 'xls']
    column_labels = dict(name='Location Name', other_details='Other Details')
    column_filters = ['id', 'name', 'other_details',
                      'time_created', 'time_updated']
    page_size = 20
    column_exclude_list = ['time_created', 'time_updated']
    column_searchable_list = ['name', 'other_details']
    column_editable_list = ['name', ]
    form_excluded_columns = ['time_created', 'time_updated']
    form_args = {
        'name': {
            'label': 'Location Name'
        },
        'other_details': {
            'label': 'Other Details'
        }
    }
    form_widget_args = {
        'other_details': {
            'rows': 10,
            'style': 'color: black'
        }
    }

class ModelViewProductMovement(ModelView):
    can_delete = False
    can_edit = False
    can_view_details = True
    can_export = True
    export_types = ['csv']
    page_size = 20
    can_set_page_size = True
    column_exclude_list = ['time_created', 'time_updated']
    column_editable_list = ['qty']
    form_excluded_columns = ['time_created', 'time_updated']

    def on_model_change(self, form, model, is_created):
        if is_created:
            conn = engine.connect()
            trans = conn.begin()
            if not form.from_location.data and not form.to_location.data:
                conn.close()
                raise validators.ValidationError('Both "From Location" and "To Location" cannot be empty')
            if form.to_location.data:
                select_st = db.text(
                    'SELECT * FROM product_stock WHERE location_id = :l AND product_id = :p')
                res = conn.execute(
                    select_st, p=form.product.data.id, l=form.to_location.data.id)
                row_to = res.fetchone()
                if row_to:
                    q = db.text(
                        'UPDATE product_stock SET available_stock = product_stock.available_stock + (1*:qty) WHERE id = :id')
                    conn.execute(q, qty=form.qty.data, id=row_to.id)
                else:
                    q = db.text(
                        'INSERT INTO product_stock (location_id, product_id, available_stock) VALUES (:l,:p,:qty)')
                    conn.execute(
                        q, qty=form.qty.data, l=form.to_location.data.id, p=form.product.data.id)
            if form.from_location.data:
                select_st = db.text(
                    'SELECT * FROM product_stock WHERE location_id = :l AND product_id = :p')
                res = conn.execute(
                    select_st, p=form.product.data.id, l=form.from_location.data.id)
                row_from = res.fetchone()
                if row_from:
                    if row_from.available_stock < form.qty.data:
                        raise validators.ValidationError('Stock of "'+ form.product.data.name +'" available at "'+ form.from_location.data.name +'" is '+ str(row_from.available_stock))
                    q = db.text(
                        'UPDATE product_stock SET available_stock = product_stock.available_stock + (1*:qty) WHERE id = :id')
                    conn.execute(q, qty=-form.qty.data, id=row_from.id)
                else:
                    raise validators.ValidationError('Zero Stock of "'+ form.product.data.name +'" available at "'+ form.from_location.data.name +'"')
            trans.commit()
            conn.close()
        else:
            conn = engine.connect()
            trans = conn.begin()
            select_st = db.select([ProductMovement]).where(
                ProductMovement.id == model.list_form_pk)
            res = conn.execute(select_st)
            row = res.fetchone()
            q = db.text(
                'UPDATE product_stock SET available_stock = product_stock.available_stock + (1*:qty) WHERE location_id = :l AND product_id = :p')
            if row.from_location_id:
                select_st = db.text(
                    'SELECT * FROM product_stock WHERE location_id = :l AND product_id = :p')
                res = conn.execute(
                    select_st, p=row.product_id, l=row.from_location_id)
                row_from = res.fetchone()
                if row_from:
                    if row_from.available_stock + (int(row.qty)-int(form.qty.data)) < 0:
                        raise validators.ValidationError('Insufficient stock at "from_location". Stock available is: '+ str(row_from.available_stock))
                    conn.execute(q, qty=(int(row.qty)-int(form.qty.data)),
                             l=row.from_location_id, p=row.product_id)
                else:
                    raise validators.ValidationError('Insufficient stock at "from_location". Stock available is: 0')
            if row.to_location_id:
                select_st = db.text(
                    'SELECT * FROM product_stock WHERE location_id = :l AND product_id = :p')
                res = conn.execute(
                    select_st, p=row.product_id, l=row.to_location_id)
                row_to = res.fetchone()
                if row_to:
                    if (row_to.available_stock + int(form.qty.data)-int(row.qty)) < 0:
                        raise validators.ValidationError('Insufficient stock at "to_location". Stock available is: '+ str(row_to.available_stock))
                    conn.execute(q, qty=(int(form.qty.data)-int(row.qty)),
                             l=row.to_location_id, p=row.product_id)
                else:
                    if int(form.qty.data)-int(row.qty) < 0:
                        raise validators.ValidationError('Insufficient stock at "to_location". Stock available is: 0')
                    q = db.text(
                        'INSERT INTO product_stock (location_id, product_id, available_stock) VALUES (:l,:p,:qty)')
                    conn.execute(
                        q, qty=(int(form.qty.data)-int(row.qty)), l=row.to_location_id, p=row.product_id)
            trans.commit()
            conn.close()

class ModelViewProductStock(ModelView):
    can_delete = False
    can_edit = False
    can_create = False
    column_exclude_list = ['time_created', 'time_updated']
    column_sortable_list = ('available_stock', )
    column_default_sort = 'product_id'
    page_size = 35
    can_export = True
    export_types = ['csv']

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.TEXT)
    time_created = db.Column(db.TIMESTAMP, server_default=db.func.now())
    time_updated = db.Column(
        db.TIMESTAMP, onupdate=db.func.now(), server_default=db.func.now())

    def __str__(self):
        return "{}".format(self.name)

    def __repr__(self):
        return "{}: {}".format(self.id, self.__str__())

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    other_details = db.Column(db.TEXT)
    time_created = db.Column(db.TIMESTAMP, server_default=db.func.now())
    time_updated = db.Column(
        db.TIMESTAMP, onupdate=db.func.now(), server_default=db.func.now())

    def __str__(self):
        return "{}".format(self.name)

    def __repr__(self):
        return "{}: {}".format(self.id, self.__str__())

class ProductMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movement_date = db.Column(db.Date, server_default=db.func.now())
    from_location_id = db.Column(db.Integer(), db.ForeignKey(Location.id))
    to_location_id = db.Column(db.Integer(), db.ForeignKey(Location.id))
    product_id = db.Column(
        db.Integer(), db.ForeignKey(Product.id), nullable=False)
    from_location = db.relationship(Location, foreign_keys=[from_location_id])
    to_location = db.relationship(Location, foreign_keys=[to_location_id])
    product = db.relationship(Product, foreign_keys=[product_id])
    qty = db.Column(db.Integer(), db.CheckConstraint(
        'qty >= 0'), nullable=False)
    time_created = db.Column(db.TIMESTAMP, server_default=db.func.now())
    time_updated = db.Column(
        db.TIMESTAMP, onupdate=db.func.now(), server_default=db.func.now())

    def __str__(self):
        return "{}".format(self.id)

class ProductStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey(Location.id))
    product_id = db.Column(db.Integer, db.ForeignKey(Product.id))
    available_stock = db.Column(db.Integer, db.CheckConstraint(
        'available_stock>=0'), nullable=False)
    location = db.relationship(Location, foreign_keys=[location_id])
    product = db.relationship(Product, foreign_keys=[product_id])
    time_created = db.Column(db.TIMESTAMP, server_default=db.func.now())
    time_updated = db.Column(
        db.TIMESTAMP, onupdate=db.func.now(), server_default=db.func.now())
    db.UniqueConstraint('location_id', 'product_id',
                        name='product_stock_location_id_product_id_uindex')


admin = Admin(app, name='Distress Relief',
              template_mode='bootstrap3', url='/', base_template='admin/custombase.html')
admin.add_view(ModelViewProductMovement(
    ProductMovement, db.session, name='Product Movement'))
admin.add_view(ModelViewProductStock(
    ProductStock, db.session, name='Product Stock'))
admin.add_view(ModelViewProduct(Product, db.session, category="Master"))
admin.add_view(ModelViewLocation(Location, db.session, category="Master"))


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='icon.png'))


# init demo data
def create_demo_data():
    products_demo_data = [
        {'name': 'First aid supplies', 'description': 'Sealed box of basic first aid necessities- iodine, bandages, painkillers, cotton, etc'},
        {'name': 'Toiletries', 'description': 'Soap, shampoo, hand sanitizer, etc'},
        {'name': 'Blankets',
            'description': 'Bedsheets, shawls, blankets'},
        {'name': 'Clothing', 'description': 'Segregate by adult and child sizes'},
        {'name': 'Canned or dry foods', 'description': 'Non perishable items'},
        {'name': 'Torches',
            'description': 'Portable light sources'},
        {'name': 'Bottled water', 'description': 'Available drinking water in liters '},
        {'name': 'Menstrual products', 'description': 'Products for female menstrual health'},
        {'name': 'Bags', 'description': 'Sturdy bags for carrying around goods'},
        {'name': 'Undergarments', 'description': 'New packaged undergarments'},
        {'name': 'Cleaning supplies', 'description': 'Bleach, iodine tablets, etc'},
        {'name': 'Plastic buckets and mugs',
            'description': 'Containers to store clean water'},
        # {'name': '', 'description': ''},
        # {'name': '', 'description': ''},
        # {'name': '', 'description': ''},
        # {'name': '', 'description': ''},
    ]
    for demo_product in products_demo_data:
        product = Product()
        product.name = demo_product['name']
        product.description = demo_product['description']
        db.session.add(product)

    location_demo_data = [
        {'name': 'Malayala Manorama office',
            'other_details': 'Eranakulam, Kerala'},
        {'name': 'Primary Health Center ',
            'other_details': 'Madikeri, Karnataka'},
        {'name': 'Red cross home', 'other_details': 'Bengaluru, Karnataka'},
        {'name': 'Relief center 1',
            'other_details': 'Eg. area 1 '},
        {'name': 'Relief center 2',
            'other_details': 'Eg. area 2 '},
        {'name': 'Relief center 3',
            'other_details': 'Eg. area 3 '},
        {'name': 'Relief center 4',
            'other_details': 'Eg. area 4 '},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
        # {'name':'', 'other_details': ''},
    ]
    for demo_location in location_demo_data:
        location = Location()
        location.name = demo_location['name']
        location.other_details = demo_location['other_details']
        db.session.add(location)

    movement_demo_data = [
        ["2017-06-08", None,	1,	    2,	120],
        ["2017-06-08", None,	2,	    1,	93],
        ["2017-06-08", None,	3,	    1,	40],
        ["2017-06-08", None,	3,	    1,	27],
        ["2017-06-08", None,	1,	    12,	20],
        ["2017-06-08", None,	3,	    3,	13],
        ["2017-06-08", None,	2,	    9,	25],
        ["2017-06-08", None,	1,	    11,	45],
        ["2017-06-08", None,	3,	    6,	15],
        ["2017-09-13", 1,	    4,	    12,	200],
        ["2017-10-12", 1,	    5,	    12,	35],
        ["2017-10-22", 2,	    7,	    1,	60],
        ["2017-11-27", 3,	    6,	    1,	55],
        ["2018-12-27", 1,	    3,	    2,	143],
        ["2018-01-09", 7,	    None,	1,	25],
        ["2018-03-07", 6,	    None,	1,	21],
        ["2018-05-31", 3,	    5,	    3,	31],
        ["2018-06-11", 1,	    6,	    12,	103],
        ["2018-07-24", 1,	    4,	    2,	65],
        ["2018-07-28", 3,	    None,	6,	25],
        ["2018-07-31", 4,	    None,	2,	25],
        ["2018-11-25", 4,	    5,	    2,	32]
    ]
    for demo_movement in movement_demo_data:
        product_movement = ProductMovement()
        product_movement.movement_date = demo_movement[0]
        product_movement.from_location_id = demo_movement[1]
        product_movement.to_location_id = demo_movement[2]
        product_movement.product_id = demo_movement[3]
        product_movement.qty = demo_movement[4]
        db.session.add(product_movement)

    product_stock_demo_data = [
        [1,	2,	210, ],
        [1,	11,	400, ],
        [1,	12,	120, ],
        [2,	1,	300, ],
        [2,	9,	270, ],
        [3,	1,	260, ],
        [3,	2,	280, ],
        [3,	3,	100, ],
        [3,	6,	367, ],
        [4,	2,	100, ],
        [4,	12,	267, ],
        [5,	2,	313, ],
        [5,	3,	343, ],
        [5,	12,	134, ],
        [6,	1,	113, ],
        [6,	12,	233, ],
        [7,	1,	234, ]
    ]
    for demo_product_stock in product_stock_demo_data:
        product_stock = ProductStock()
        product_stock.location_id = demo_product_stock[0]
        product_stock.product_id = demo_product_stock[1]
        product_stock.available_stock = demo_product_stock[2]
        db.session.add(product_stock)
    
    db.session.commit()
    return


if __name__ == "__main__":
    # create demo data if demo flag set
    if app.config['demo']:
        db.drop_all()
        db.create_all()
        create_demo_data()
    debug = not (app.config['is_production'])
    app.run(debug=debug)
