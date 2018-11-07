import argparse
import numpy as np
import ray
import time


NUM_CPUS = 4


def get_partition(index, element, num_reducers):
    return index % num_reducers

@ray.remote
def generate_dependencies(data_size):
    return np.random.rand(data_size)

@ray.remote
def warmup(dependencies):
    time.sleep(1)


@ray.remote
def map_step(batch):
    out = np.array([e for e in batch])
    return out

@ray.remote
def shuffle(num_reducers, *batches):
    partitions = [[] for _ in range(num_reducers)]
    for batch in batches:
        for i, e in enumerate(batch):
            partitions[get_partition(i, e, num_reducers)].append(e)
    return partitions

@ray.remote
class Reducer(object):
    def __init__(self, reduce_index):
        self.reduce_index = reduce_index
        self.sum = 0

    def reduce(self, *partitions):
        for partition in partitions:
            self.sum += sum(partition[self.reduce_index])

    def get_sum(self):
        return self.sum


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--num-nodes', type=int, required=True)
    parser.add_argument('--num-maps', type=int, default=1)
    parser.add_argument('--num-reducers', type=int, default=1)
    parser.add_argument('--num-iterations', type=int, default=100)
    parser.add_argument('--data-size', type=int, default=100)
    args = parser.parse_args()


    ray.worker._init(
            start_ray_local=True,
            num_local_schedulers=args.num_nodes,
            num_cpus=NUM_CPUS
            )

    dependencies = generate_dependencies.remote(args.data_size)
    for i in range(args.num_nodes):
        for j in range(NUM_CPUS):
            warmup.remote(dependencies)
    reducers = [Reducer.remote(i) for i in range(args.num_reducers)]

    for _ in range(args.num_iterations):
        # Submit map tasks.
        map_ins = [dependencies for _ in range(args.num_nodes)]
        for i in range(args.num_maps):
            map_outs = []
            for j in range(args.num_nodes):
                map_outs.append(map_step.remote(map_ins[j]))
            map_ins = map_outs

        # Shuffle data and submit reduce tasks.
        shuffled = [shuffle.remote(len(reducers), map_in) for map_in in map_ins]
        [reducer.reduce.remote(*shuffled) for reducer in reducers]

        time.sleep(0.1)
    print(ray.get([reducer.get_sum.remote() for reducer in reducers]))
