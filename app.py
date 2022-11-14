from datetime import timedelta, datetime
import redis
from flask import Flask, jsonify, request, make_response
import pymongo
from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import jwt_required
from flask_jwt_extended import JWTManager

ACCESS_EXPIRES = timedelta(hours=1)

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "secretkeyenlacenturia"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = ACCESS_EXPIRES
jwt = JWTManager(app)
client = pymongo.MongoClient("mongodb+srv://m001-student:m001-mongodb-basics@sandbox.ymprapn.mongodb.net/test")
db = client.flask
logs = db.logins
movs = db.movies

jwt_redis_blocklist = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(jti)
    return token_in_redis is not None

@app.route('/register')
def register():
    auth = request.authorization

    if auth and auth.password:
        logs.insert_one({'user': auth.username, 'password': auth.password})
        return jsonify(msg="User created")
    return make_response('Could not verify!', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.route('/login')
def login():
    auth = request.authorization
    if auth and auth.password:
        x = logs.find_one({'user': auth.username})

        try:
            if x['user'] == auth.username and x['password'] == auth.password:
                access_token = create_access_token(identity=auth.username)
                return access_token
        except:
            return make_response('Wrong username and password', 401,{'WWW-Authenticate': 'Basic realm="Login Required"'})
    return make_response('Could not verify!', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.route("/logout", methods=["DELETE"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    print(jti)
    jwt_redis_blocklist.set(jti, "", ex=ACCESS_EXPIRES)
    return jsonify(msg="Access token revoked")

@app.route('/unprotected')
def unprotected():
    return jsonify({'message' : 'Anyone can view this!'})

@app.route('/protected',methods=['POST'])
@jwt_required()
def protected():
    return jsonify({'message' : 'This is only available for people with valid tokens.'})

@app.route('/add_movie', methods=['POST'])
@jwt_required()
def add_movie():
    movie_data = request.get_json()
    new_movie = movie_data
    movs.insert_one(new_movie)
    title = new_movie["Title"]
    print(title)
    logs.update_many({}, {"$set": {title: False}})
    return 'Done', 201

@app.route('/update_movie', methods=['POST'])
@jwt_required()
def update_movie():
    title = request.values.get("Title", type=str, default=None)
    genre = request.values.get("Genre", type=str, default=None)
    release = request.values.get("Release Date", type=str, default=None)
    review = request.values.get("Review", type=str, default=None)
    movs.update_one({'Title': title}, {"$set":{"Genre":genre}})
    movs.update_one({'Title': title}, {"$set": {"Release Date": release}})
    movs.update_one({'Title': title}, {"$set": {"Review": review}})
    return 'Done', 201

@app.route('/delete_movie', methods=['POST'])
@jwt_required()
def delete_movie():
    moviename = request.values.get("Title", type=str, default=None)
    moviecheck = movs.find_one({'Title': moviename})
    movs.delete_one(moviecheck)
    return 'Movie Deleted Successfully', 201


@app.route('/movies', methods=['GET'])
def movies():
    movie_list = movs.find()
    movies = [{k: v[k] for k in v if k != '_id'} for v in movie_list]
    return jsonify(movies)

@app.route('/upvote-downvote', methods=['POST'])
@jwt_required()
def votes():
    user_id = get_jwt_identity()
    user_check =  logs.find_one({'user': user_id})
    moviename = request.values.get("Title", type=str, default=None)
    print(type(moviename))
    vote = request.values.get("Vote", type=int, default=None)
    if not user_check[moviename]:
        if vote == 1:
            upvotes = movs.update_one({'Title': moviename}, {"$inc":{"Upvote":1}})
        elif vote == 0:
            downvotes = movs.update_one({'Title': moviename}, {"$inc":{"Downvote":1}})
        logs.update_one({'user': user_id}, {"$set": {moviename: True}})
        return 'Voted Successfully', 201
    else:
        return 'Already Voted', 201

@app.route('/sortmoviesbydate', methods=['GET'])
def sortbydate():
    movie_list = movs.find()
    movie_list = list(movie_list)
    print(movie_list)
    for movie in movie_list:
        movie["Release Date"] = datetime.strptime(movie["Release Date"], "%d/%m/%Y").date()
    sortedmovies = sorted(movie_list,key=lambda i:i["Release Date"])
    sortedmovieslist = [{k: v[k] for k in v if k != '_id'} for v in sortedmovies]
    return jsonify(sortedmovieslist)

@app.route('/sortmoviesbygenre', methods=['GET'])
def sortbygenre():
    movie_list = movs.find()
    movie_list = list(movie_list)
    print(movie_list)
    sortedmovies = sorted(movie_list,key=lambda i:i["Genre"])
    sortedmovieslist = [{k: v[k] for k in v if k != '_id'} for v in sortedmovies]
    return jsonify(sortedmovieslist)

@app.route('/setfavgenre', methods=['POST'])
@jwt_required()
def favgenre():
    genre = request.values.get("Genre", type=str, default=None)
    favgenre = movs.find({"Genre":genre})
    favgenre = list(favgenre)
    favgenrelist = [{k: v[k] for k in v if k != '_id'} for v in favgenre]
    return jsonify(favgenrelist)

if __name__ == '__main__':
    app.run(debug=True)

