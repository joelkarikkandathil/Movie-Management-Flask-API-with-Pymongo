from datetime import timedelta, datetime
import redis
from flask import Flask, jsonify, request, make_response
import pymongo
from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import get_jwt
from flask_jwt_extended import jwt_required
from flask_jwt_extended import JWTManager
from bson.objectid import ObjectId

ACCESS_EXPIRES = timedelta(hours=1)

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "secretkeyenlacenturia"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = ACCESS_EXPIRES
jwt = JWTManager(app)
client = pymongo.MongoClient("mongodb+srv://m001-student:m001-mongodb-basics@sandbox.ymprapn.mongodb.net/test")
db = client.flask
logs = db.logins
movs = db.movies
vots = db.votes

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
        movies = movs.find()
        for movie in movies:
            id = movie['ID']
            logs.update_one({'user': auth.username}, {"$set":{id: False}})
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
    title = request.values.get("Title", type=str, default=None)
    genre = request.values.get("Genre", type=str, default=None)
    reldate = request.values.get("Release Date", type=str, default=None)
    review = request.values.get("Review", type=str, default=None)
    id = movs.insert_one({"Title": title,"Genre": genre, "Release Date": reldate, "Review": review})
    movid = id.inserted_id
    movids = str(movid)
    movs.update_one({"Title": title}, {"$set": {"ID": movids}})
    logs.update_many({}, {"$set": {movids: False}})
    output = {'Movie ID': movids}
    return jsonify("Movie added successfully", output)

@app.route('/update_movie', methods=['POST'])
@jwt_required()
def update_movie():
    id = request.values.get("ID", type=str, default=None)
    title = request.values.get("Title", type=str, default=None)
    genre = request.values.get("Genre", type=str, default=None)
    reldate = request.values.get("Release Date", type=str, default=None)
    movs.update_one({'_id': ObjectId(id)}, {"$set": {"Title": title, "Genre": genre, "Release Date": reldate}})
    output = movs.find_one({'_id': ObjectId(id)})
    return jsonify("Movie updated successfully")

@app.route('/delete_movie', methods=['DELETE'])
@jwt_required()
def delete_movie():
    id = request.values.get("ID", type=str, default=None)
    moviecheck = movs.find_one({'_id': ObjectId(id)})
    movs.delete_one(moviecheck)
    logs.update_one({'_id': ObjectId(id)}, {"$unset": {id: 1}})
    return jsonify("Movie Deleted Successfully")


@app.route('/movies', methods=['GET'])
def movies():
    movie_list = movs.find()
    movies = [{k: v[k] for k in v if k != '_id'} for v in movie_list]
    return jsonify(movies)

@app.route('/upvote-downvote', methods=['POST'])
@jwt_required()
def votes():
    user_id = get_jwt_identity()
    upvoter_list = ["Upvoters:-"]
    downvoter_list = ["Downvoters:-"]
    user_check = logs.find_one({'user': user_id})
    print(user_check)
    movieid = request.values.get("ID", type=str, default=None)
    moviecheck = movs.find_one({'_id': ObjectId(movieid)})
    print(moviecheck)
    vote = request.values.get("Vote", type=int, default=None)
    if not user_check[movieid]:
        if vote == 1:
            upvotes = movs.update_one({'_id': ObjectId(movieid)}, {"$inc": {"Upvote":1}})
            if not vots.find_one({'Movie ID': movieid}):
                vots.insert_one({'Movie ID': movieid, 'Movie Name': moviecheck['Title']})
            vots.update_one({'Movie ID': movieid}, {"$push": {"Upvoters": user_check['user']}})
        elif vote == 0:
            downvotes = movs.update_one({'_id': ObjectId(movieid)}, {"$inc": {"Downvote":1}})
            if not vots.find_one({'Movie ID': movieid}):
                vots.insert_one({'Movie ID': movieid, 'Movie Name': moviecheck['Title']})
            vots.update_one({'Movie ID': movieid}, {"$push": {"Downvoters": user_check['user']}})
        logs.update_one({'user': user_id}, {"$set": {movieid: True}})
        output = vots.find_one({'Movie ID': movieid})
        upvoter_list.append(output['Upvoters'])
        downvoter_list.append(output['Downvoters'])
        return jsonify("Voted Successfully", upvoter_list, downvoter_list)
    else:
        output = vots.find_one({'Movie ID': movieid})
        upvoter_list.append(output['Upvoters'])
        downvoter_list.append(output['Downvoters'])
        return jsonify("Already voted", upvoter_list, downvoter_list)

@app.route('/sortmovies', methods=['POST'])
def sortbydate():
    movie_list = movs.find()
    movie_list = list(movie_list)
    sorttype = request.values.get("Sort Type", type=str, default=None)
    if sorttype == "date":
         for movie in movie_list:
            movie["Release Date"] = datetime.strptime(movie["Release Date"], "%d/%m/%Y").date()
         sortedmovies = sorted(movie_list,key=lambda i:i["Release Date"])
         sortedmovieslist = [{k: v[k] for k in v if k != '_id' and  k != 'ID'} for v in sortedmovies]
         return jsonify(sortedmovieslist)
    elif sorttype == "genre":
        sortedmovies = sorted(movie_list, key=lambda i: i["Genre"])
        sortedmovieslist = [{k: v[k] for k in v if k != '_id' and  k != 'ID'} for v in sortedmovies]
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
