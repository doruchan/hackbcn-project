from flask import Flask, jsonify, request, abort, url_for,  send_from_directory
from flask_caching import Cache
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
import os

from levelaccess.api import get_mapillary_images, get_coordinates

app = Flask("levelaccess")
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///places.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["UPLOAD_EXTENSIONS"] = [".jpg", ".png"]
app.config["UPLOAD_PATH"] = "../images"
db = SQLAlchemy(app)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})
migrate = Migrate(app, db)

_IMAGE_DIR = os.path.realpath(app.config["UPLOAD_PATH"])

class Place(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    lat = db.Column(db.Float(), nullable=False)
    lon = db.Column(db.Float(), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    picture_url = db.Column(db.String(200))
    probability = db.Column(db.Float())
    probability_reason = db.Column(db.String(500))

    def __repr__(self):
        return f'<Place {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'lat': self.lat,
            'lon': self.lon,
            'type': self.type,
            'probability': self.probability,
            'probability_reason': self.probability_reason,
            'picture_url': self.image_url,
        }

    @hybrid_property
    def image_url(self):
        path = self.picture_url

        if path is not None and not path.startswith("http"):
            return url_for("images", filename=path, _external=True)
        return path


# Create the database tables
with app.app_context():
    db.create_all()


def add_place(data):
    new_place = Place(**data)
    db.session.add(new_place)
    db.session.commit()


@app.route('/')
def home():
    return "Hello, World!"


def _get_image(place):
    if place.picture_url is None:
        pic_name = place.name.lower().replace(" ", "_") + ".jpg"
        existing = os.listdir(_IMAGE_DIR)

        if pic_name in existing:
            place.picture_url = pic_name
            db.session.commit()
            return place.picture_url
   
        lat = place.lat
        lon = place.lon
        image_path = get_mapillary_images(lat, lon)
        
        place.picture_url = image_path
        db.session.commit()
    return place.picture_url


@app.route('/images/<filename>')
def images(filename):
    print("images", filename)
    print(_IMAGE_DIR)
    return send_from_directory(_IMAGE_DIR, filename)


@app.route('/image/<int:place_id>')
def get_image(place_id):
    place = Place.query.get(place_id)
    if place is None:
        abort("Place not found")

    return _get_image(place)


@app.route('/calculate/<int:place_id>')
def calculate(place_id):
    place = Place.query.get(place_id)
    if place is None:
        abort("Place not found")
    
    _get_image(place)
    
    # send to model
    place.probability = 1
    place.probability_reason = "bla bla"
    return jsonify(place.to_dict()), 200


@app.route('/place/<int:place_id>', methods=['PUT'])
def update_place(place_id):
    place = Place.query.get(place_id)
    if place is None:
        abort(404, description="Place not found")
    
    data = request.json

    for key, value in data.items():
        setattr(place, key, value)
    
    db.session.commit()
    return jsonify(place.to_dict()), 200


@cache.cached(timeout=300)
@app.route('/places', methods=['GET'])
def get_places():
    places = Place.query.all()
    return jsonify([place.to_dict() for place in places])


@cache.cached(timeout=300, key_prefix='place')
@app.route('/place/<int:place_id>', methods=['GET'])
def get_place(place_id):
    place = Place.query.get(place_id)
    if place is None:
        abort(404, description="Place not found")
    return jsonify(place.to_dict())


@cache.cached(timeout=300, key_prefix='search')
@app.route('/search/<query>', methods=['GET'])
def search(query):
    location = get_coordinates(query)
    data = location.raw
    existing = Place.query.filter_by(name=data['name']).first()
    if existing:
        return existing.to_dict()
    new_place = add_place(location.raw)
    return jsonify(new_place.to_dict())


@app.route('/add_place/<query>', methods=['GET'])
def add_place(query):
    location = get_coordinates(query)
    new_place = add_place(location.raw)
    return jsonify({"message": "Place added successfully", "place": new_place.to_dict()}), 201


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
