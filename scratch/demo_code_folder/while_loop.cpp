#include <iostream>
using namespace std;

int main() {
    int n = 10, sum = 0, i = 1;
    while (i <= n) {
        if (i % 2 == 0) sum += i;
        i++;
    }
    cout << "Even sum: " << sum << endl;
    return 0;
}
