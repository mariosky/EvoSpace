__author__ = 'mariosky'

LOGGING = False
LOG_INTERVAL = 10
LOCAL = False

import os, redis, random


redis_url = os.getenv('REDISCLOUD_URL', 'redis://localhost:6379')
r = redis.from_url(redis_url)

#r = redis.Redis(host=HOST, port=PORT, db=DB)

class Individual:
    def __init__(self, **kwargs):
        self.id = kwargs['id']
        self.fitness = kwargs.get('fitness',{})
        self.chromosome = kwargs.get('chromosome',[])
        self.__dict__.update(kwargs)


    def put(self, population):
        pipe = r.pipeline()
        if pipe.sadd( population, self.id ):
            pipe.set( self.id , self.__dict__ )
            pipe.execute()
            return True
        else:
            return False


    def get(self, as_dict = False):
        if r.get(self.id):
            _dict = eval(r.get(self.id))
            self.__dict__.update(_dict)
        else:
            raise LookupError("Key Not Found")

        if as_dict:
            return self.__dict__
        else:
            return self


    def __repr__(self):
        return self.id +":"+ str(self.fitness) +":" + str( self.chromosome)


    def as_dict(self):
        return self.__dict__


class Population:
    def __init__(self, name = "pop" ):
        self.name = name
        self.sample_counter = self.name+':sample_count'
        self.individual_counter = self.name+':individual_count'
        self.sample_queue = self.name+":sample_queue"
        self.returned_counter = self.name+":returned_count"
        self.log_queue = self.name+":log_queue"


    def get_returned_counter(self):
        return int( r.get(self.returned_counter))


    def individual_next_key(self):
        key = r.incr(self.individual_counter)
        return self.name+":individual:%s" % key


    def size(self):
        return r.scard(self.name)


    def initialize(self):
        r.flushall()
        r.setnx(self.sample_counter,0)
        r.setnx(self.individual_counter,0)
        r.setnx(self.returned_counter,0)
        r.set(self.name+":found",0)


    def get_sample(self, size):
        sample_id = r.incr(self.sample_counter)

        #Get keys
        sample = [r.spop(self.name) for i in range(size)]
        #If there is a None
        if None in sample:
            sample = [s for s in sample if s]
            if not sample:
                return None
        r.sadd(self.name+":sample:%s" % sample_id, *sample)
        r.rpush(self.sample_queue, self.name+":sample:%s" % sample_id)
        try:
            result =  {'sample_id': self.name+":sample:%s" % sample_id ,
                       'sample':   [Individual(id=key).get(as_dict=True) for key in sample ]}
        except:
            return None
        return result


    def read_sample_queue(self):
        result = r.lrange(self.sample_queue,0,-1)
        return result


    def read_sample_queue_len(self):
        return r.llen(self.sample_queue)


    def read_pop_keys(self):
        sample = r.smembers(self.name)
        sample = list(sample)
        result =  { 'sample': sample }
        return result


    def read_all(self):
        sample = r.smembers(self.name)
        result =  { 'sample':   [Individual(id=key).get(as_dict=True) for key in sample]}
        return result


    def put_individual(self, **kwargs ):
        if kwargs['id'] is None:
            kwargs['id'] = self.name+":individual:%s" % r.incr(self.individual_counter)
        ind = Individual(**kwargs)
        ind.put(self.name)


    def put_sample(self,sample):
        if not isinstance(sample,dict):
            raise TypeError("Samples must be dictionaries")

        r.incr(self.returned_counter)

        if LOGGING:
            count = r.incr(self.returned_counter)
            if count % LOG_INTERVAL == 0 :
                r.sunionstore("log:"+str(count),"pop")

        for member in sample['sample']:
            if member['id'] is None:
                member['id'] = self.name+":individual:%s" % r.incr(self.individual_counter)
            self.put_individual(**member)
        r.delete(sample['sample_id'])
        r.lrem(self.sample_queue,sample['sample_id'])


    def respawn_sample(self, sample_id):
        if r.exists(sample_id):
            members = r.smembers(sample_id)
            r.sadd(self.name, *members)
            r.delete(sample_id)
            r.lrem(self.sample_queue,sample_id,1)


    def respawn_ratio(self, ratio = .2):
        until_sample  = int(r.llen(self.sample_queue)*ratio)
        for i in range(until_sample):
            self.respawn_sample( r.lpop(self.sample_queue))


    def respawn(self, n = 1):
        current_size = r.llen(self.sample_queue)
        if n > current_size:
            for i in range(current_size):
                self.respawn_sample( r.lpop(self.sample_queue))
        else:
            for i in range(n):
                self.respawn_sample( r.lpop(self.sample_queue))


    def found(self):
        r.get(self.name+":found")


    def found_it(self):
        r.set(self.name+":found",1)

def init_pop( populationSize, rangemin = 0 ,rangemax = 11, listSize = 66):
    server = Population("pop")
    server.initialize()
    for individual in range(populationSize):
        chrome = [random.randint(rangemin,rangemax) for _ in range(listSize)]
        individual = {"id":None,"fitness":{"DefaultContext":0.0 },"chromosome":chrome}
        server.put_individual(**individual)

if __name__ == "__main__":
    init_pop(100)

