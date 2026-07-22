#include <stdlib.h>
typedef struct node{int v;}node;
node*mk(int v){node*n=malloc(sizeof(node));n->v=v;return n;}
int print_prealloc(node*item,char*buffer,int length){return 1;}
void del(node*n){free(n);}
